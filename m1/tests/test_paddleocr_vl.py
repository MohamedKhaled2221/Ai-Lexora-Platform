"""Adapter tests that need no model weights.

The parts of ``src.paddleocr_vl`` that can be wrong without anyone noticing are
the ones that translate PaddleOCR-VL's result shape into the pipeline's -- block
objects that are *not* dict-like, table HTML that arrives in two different
places, and layout labels that must be dropped. Those are what is tested here.
Inference itself is exercised by ``scripts/paddleocr_vl_benchmark.py``, which
needs a 1.8 GB checkpoint and does not belong in the suite.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.config import PipelineConfig
from src.paddleocr_vl import (
    _block_bbox,
    _block_label,
    _block_text,
    _blocks,
    _strip_html,
    _tables_from_result,
    page_tables,
    parse_table_html,
    run_paddleocr_vl,
)


class Block:
    """Stand-in for ``PaddleOCRVLBlock``: attributes, and deliberately not a Mapping."""

    def __init__(self, label, bbox, content):
        self.label = label
        self.bbox = bbox
        self.content = content


def test_blocks_read_object_form():
    # dict(block) on the real class yields {}, which silently produced an empty
    # page before this was handled. Guard it.
    block = Block("text", [1, 2, 3, 4], "hello")
    assert _block_text(block) == "hello"
    assert _block_label(block) == "text"
    assert _block_bbox(block) == (1.0, 2.0, 3.0, 4.0)


def test_blocks_read_dict_form():
    block = {"block_label": "TEXT", "block_bbox": [1, 2, 3, 4], "block_content": "hi"}
    assert _block_text(block) == "hi"
    assert _block_label(block) == "text"
    assert _block_bbox(block) == (1.0, 2.0, 3.0, 4.0)


def test_block_bbox_accepts_a_quad():
    block = Block("text", [10, 20, 30, 20, 30, 40, 10, 40], "x")
    assert _block_bbox(block) == (10.0, 20.0, 30.0, 40.0)


def test_blocks_finds_the_list_under_any_known_key():
    assert _blocks({"parsing_res_list": [1, 2]}) == [1, 2]
    assert _blocks({"parsing_result": [3]}) == [3]
    assert _blocks({"nothing": []}) == []


TABLE = """<table><tr><td>الاسم</td><td>Amount</td></tr>
<tr><td>عقد</td><td>1,000</td></tr></table>"""


def test_parse_table_html_shape_and_cells():
    table = parse_table_html(TABLE)
    assert (table.rows, table.cols) == (2, 2)
    assert table.cells[0] == ["الاسم", "Amount"]
    assert table.cells[1][1] == "1,000"


def test_strip_html_flattens_rows_for_scoring():
    # CER compares against a plain-text reference, so markup has to become one
    # line per row rather than one blob.
    assert _strip_html(TABLE).splitlines() == ["الاسم Amount", "عقد 1,000"]


def test_tables_from_result_reads_the_separate_list():
    payload = {"table_res_list": [{"pred_html": TABLE}, {"pred_html": "no table here"}]}
    assert _tables_from_result(payload) == [TABLE]


def test_run_returns_an_error_result_rather_than_raising():
    class Exploding:
        def predict(self, _):
            raise RuntimeError("boom")

    img = np.zeros((10, 10, 3), dtype=np.uint8)
    res = run_paddleocr_vl(img, 1, 1.0, PipelineConfig().ocr, pipeline=Exploding())
    assert res.error and "boom" in res.error
    assert res.boxes == []


class FakePipeline:
    def __init__(self, payload):
        self.payload = payload

    def predict(self, _):
        return [self.payload]


def _run(payload):
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    return run_paddleocr_vl(img, 1, 1.0, PipelineConfig().ocr,
                            pipeline=FakePipeline(payload))


def test_run_maps_blocks_to_boxes_and_keeps_model_order():
    res = _run({"parsing_res_list": [
        Block("text", [0, 100, 50, 120], "second in reading order"),
        Block("doc_title", [0, 10, 50, 30], "first"),
    ]})
    assert [b.text for b in res.boxes] == ["second in reading order", "first"]
    # A generative decoder reports no score; a fabricated one would silently
    # disable the pipeline's low-confidence gate.
    assert all(b.conf == 1.0 for b in res.boxes)
    assert res.atoms == res.boxes


def test_run_drops_page_furniture():
    res = _run({"parsing_res_list": [
        Block("header", [0, 0, 10, 10], "running head"),
        Block("text", [0, 20, 10, 30], "body"),
    ]})
    assert [b.text for b in res.boxes] == ["body"]
    assert res.dropped_boxes == 1


def test_run_collects_tables_and_flattens_them_into_the_text():
    res = _run({"parsing_res_list": [Block("table", [0, 0, 10, 10], TABLE)]})
    tables = page_tables(res)
    assert len(tables) == 1
    assert (tables[0].rows, tables[0].cols) == (2, 2)
    assert "الاسم Amount" in res.text


def test_a_table_reported_twice_is_counted_once():
    res = _run({
        "table_res_list": [{"pred_html": TABLE}],
        "parsing_res_list": [Block("table", [0, 0, 10, 10], TABLE)],
    })
    assert len(page_tables(res)) == 1


@pytest.mark.parametrize("payload", [{}, {"parsing_res_list": []}])
def test_empty_result_is_empty_not_an_error(payload):
    res = _run(payload)
    assert res.boxes == []
    assert res.error is None
