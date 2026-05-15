ALTER TABLE mortgage_insights
  ADD COLUMN IF NOT EXISTS avg_2yr_rate NUMERIC,  -- BoE market avg 2yr fixed ~85% LTV
  ADD COLUMN IF NOT EXISTS avg_5yr_rate NUMERIC;  -- BoE market avg 5yr fixed ~85% LTV
