-- SSB Q2.1: revenue by year and brand, one category, suppliers in America
SELECT sum(lo_revenue) AS revenue, d_year, p_brand1
FROM lineorder, dates, part, supplier
WHERE lo_orderdate = d_datekey
  AND lo_partkey = p_partkey
  AND lo_suppkey = s_suppkey
  AND p_category = 'MFGR#12'
  AND s_region = 'AMERICA'
GROUP BY d_year, p_brand1
ORDER BY d_year, p_brand1;
