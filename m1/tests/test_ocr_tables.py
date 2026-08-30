"""Tables reconstructed from OCR geometry.

Neither table extractor in this pipeline can see an OCR'd page: Docling runs
over the source file on the text-layer route only, and PyMuPDF's
``find_tables`` reads ruling lines out of a content stream that a raster does
not have. Every table on every scanned page was therefore flattened into loose
paragraph text -- ``synthetic_table_page.png`` was the fixture that exposed it
(1 table present, 0 found).

These tests work on synthetic box geometry rather than real images, so they run
in milliseconds and pin the *algorithm* rather than one engine's output on one
fixture. The end-to-end proof is in the evaluation report's table section.
"""

from __future__ import annotations

import pytest

from src.config import OCRConfig
from src.document_chunk_schema import BoundingBox, SourceEngine
from src.ocr_pipeline import OCRBox, tables_from_atoms


def atom(text: str, x0: float, y0: float, *, w: float | None = None,
         h: float = 20, conf: float = 0.9) -> OCRBox:
    width = w if w is not None else max(len(text) * 9, 9)
    return OCRBox(
        text=text, conf=conf,
        bbox=BoundingBox(x0=x0, y0=y0, x1=x0 + width, y1=y0 + h),
        engine=SourceEngine.TESSERACT,
    )


def grid_atoms(rows: list[list[str]], col_x=(100, 400, 700, 1000), row_h=60):
    """Atoms laid out on a clean grid: wide column gaps, tight word gaps."""
    out = []
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            if not cell:
                continue
            x = col_x[c]
            for word in cell.split():
                out.append(atom(word, x, 100 + r * row_h))
                x += len(word) * 9 + 8      # a word gap, not a column gap
    return out


@pytest.fixture
def cfg() -> OCRConfig:
    return OCRConfig()


class TestDetection:
    def test_finds_a_simple_grid(self, cfg):
        rows = [["Item", "Qty", "Price"],
                ["Cable", "10", "500"],
                ["Switch", "4", "1200"],
                ["Router", "2", "3400"]]
        tables = tables_from_atoms(grid_atoms(rows), page=1, scale=1.0, cfg=cfg)
        assert len(tables) == 1
        assert tables[0].shape == (4, 3)
        assert tables[0].rows[1][0] == "Cable"

    def test_multi_word_cells_stay_in_one_cell(self, cfg):
        rows = [["Deliverable", "Owner"],
                ["Due diligence report", "Outside counsel"],
                ["Share purchase draft", "Outside counsel"]]
        tables = tables_from_atoms(grid_atoms(rows), page=1, scale=1.0, cfg=cfg)
        assert len(tables) == 1
        assert tables[0].rows[1][0] == "Due diligence report"

    def test_prose_is_not_a_table(self, cfg):
        """Justified text has wide inter-word gaps but no recurring columns."""
        atoms = []
        for r, offsets in enumerate([(100, 380, 720), (100, 520, 900),
                                     (100, 300, 640), (100, 610, 980)]):
            for x in offsets:
                atoms.append(atom("word", x, 100 + r * 60))
        assert tables_from_atoms(atoms, page=1, scale=1.0, cfg=cfg) == []

    def test_two_rows_is_not_enough(self, cfg):
        """A pair of label/value lines is a letterhead, not a table."""
        rows = [["Date", "2026-01-15"], ["Ref", "SPA/2026/04"]]
        assert tables_from_atoms(grid_atoms(rows), page=1, scale=1.0, cfg=cfg) == []

    def test_single_column_is_not_a_table(self, cfg):
        atoms = [atom("line", 100, 100 + i * 60) for i in range(6)]
        assert tables_from_atoms(atoms, page=1, scale=1.0, cfg=cfg) == []


class TestRobustness:
    def test_empty_cells_do_not_shift_columns(self, cfg):
        """The failure this guards: a gap read as "everything moves left one"."""
        rows = [["Case", "Hearing", "Outcome"],
                ["1245/2025", "", "Reserved"],
                ["1309/2025", "2026-04-22", "Adjourned"],
                ["1402/2026", "2026-06-02", ""]]
        tables = tables_from_atoms(grid_atoms(rows), page=1, scale=1.0, cfg=cfg)
        assert len(tables) == 1
        grid = tables[0].rows
        assert grid[1] == ["1245/2025", "", "Reserved"]
        assert grid[3] == ["1402/2026", "2026-06-02", ""]

    def test_low_confidence_atoms_are_dropped(self, cfg):
        """Tesseract reads a table's ruling line as column-aligned garbage.

        ``a mR + ee CS SS I`` -- perfectly aligned, and indistinguishable from a
        real row on geometry alone. Every token of it scores under 0.30.
        """
        rows = [["Item", "Qty", "Price"],
                ["Cable", "10", "500"],
                ["Switch", "4", "1200"]]
        atoms = grid_atoms(rows)
        junk_y = 100 + 3 * 60
        atoms += [atom(t, x, junk_y, conf=0.2)
                  for t, x in (("mR", 100), ("ee", 400), ("CS", 700))]
        tables = tables_from_atoms(atoms, page=1, scale=1.0, cfg=cfg)
        assert len(tables) == 1
        assert tables[0].shape == (3, 3)
        assert not any("mR" in cell for row in tables[0].rows for cell in row)

    def test_scale_free_across_dpi(self, cfg):
        """The gap threshold is a multiple of glyph height, so doubling the
        render resolution must not change the result."""
        rows = [["Item", "Qty"], ["Cable", "10"], ["Switch", "4"]]
        small = tables_from_atoms(grid_atoms(rows), page=1, scale=1.0, cfg=cfg)
        big = [
            OCRBox(text=a.text, conf=a.conf, engine=a.engine,
                   bbox=BoundingBox(x0=a.bbox.x0 * 2, y0=a.bbox.y0 * 2,
                                    x1=a.bbox.x1 * 2, y1=a.bbox.y1 * 2))
            for a in grid_atoms(rows)
        ]
        assert small[0].rows == tables_from_atoms(big, page=1, scale=0.5, cfg=cfg)[0].rows

    def test_arabic_tables_read_right_to_left(self, cfg):
        rows = [["البند", "Item", "المبلغ"],
                ["أتعاب", "Fees", "180000"],
                ["مصروفات", "Costs", "35500"]]
        tables = tables_from_atoms(grid_atoms(rows), page=1, scale=1.0, cfg=cfg)
        assert len(tables) == 1
        # Column order is reversed for Arabic-dominant content, matching the
        # convention _sort_reading_order already applies to lines.
        assert tables[0].rows[0][0] == "المبلغ"

    def test_disabled_by_config(self, cfg):
        rows = [["Item", "Qty"], ["Cable", "10"], ["Switch", "4"]]
        cfg.detect_tables = False
        assert tables_from_atoms(grid_atoms(rows), page=1, scale=1.0, cfg=cfg) == []

    def test_no_atoms_is_not_an_error(self, cfg):
        assert tables_from_atoms([], page=1, scale=1.0, cfg=cfg) == []


class TestPaddleDownscale:
    def test_oversized_pages_are_shrunk_for_paddle_only(self):
        """PaddleOCR gets a downscaled image; the scale factor compensates."""
        import numpy as np

        from src.ocr_pipeline import _fit_for_paddle

        img = np.zeros((3500, 2400, 3), dtype=np.uint8)
        out, shrink = _fit_for_paddle(img, 1600)
        assert max(out.shape[:2]) == 1600
        assert shrink == pytest.approx(3500 / 1600, rel=1e-3)

    def test_small_pages_are_untouched(self):
        import numpy as np

        from src.ocr_pipeline import _fit_for_paddle

        img = np.zeros((900, 700, 3), dtype=np.uint8)
        out, shrink = _fit_for_paddle(img, 1600)
        assert shrink == 1.0
        assert out is img

    def test_cap_can_be_disabled(self):
        import numpy as np

        from src.ocr_pipeline import _fit_for_paddle

        img = np.zeros((3500, 2400, 3), dtype=np.uint8)
        out, shrink = _fit_for_paddle(img, 0)
        assert shrink == 1.0
        assert out is img
