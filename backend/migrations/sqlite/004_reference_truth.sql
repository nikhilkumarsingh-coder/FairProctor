-- Reference (synthetic) sessions carry their true label, so the fairness report can show how often
-- honest candidates in each group were sent to review. NULL for real candidates; never a model input.
ALTER TABLE sessions ADD COLUMN ref_truth TEXT;
