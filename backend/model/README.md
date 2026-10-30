The trained scoring model used by the web backend (copied from `artifacts/` after `python -m fairproctor.pipeline`).
`priority_raws.npy` fixes the 0-100 priority scale. Retrain and copy again to update.
Pickled with scikit-learn 1.9.1: keep that version pinned in requirements.txt.
