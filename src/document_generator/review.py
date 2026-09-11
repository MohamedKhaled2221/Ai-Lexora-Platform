from .schemas import AssembledDraft, DraftStatus, ReviewDecision, ReviewRecord


def apply_review_state(draft: AssembledDraft, review: ReviewRecord) -> AssembledDraft:
    if review.draft_id != draft.draft_id:
        raise ValueError("Review does not belong to draft")

    mapping = {
        ReviewDecision.APPROVE: DraftStatus.APPROVED,
        ReviewDecision.REJECT: DraftStatus.REJECTED,
        ReviewDecision.EDIT: DraftStatus.EDITED,
    }
    draft.status = mapping[review.decision]
    return draft
