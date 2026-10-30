-- SSB Q2.3: revenue by year, one brand, suppliers in Europe
SELECT sum(lo_revenue) AS revenue, d_year, p_brand1
FROM lineorder, dates, part, supplier
WHERE lo_orderdate = d_datekey
  AND lo_partkey = p_partkey
  AND lo_suppkey = s_suppkey
  AND p_brand1 = 'MFGR#2239'
  AND s_region = 'EUROPE'
GROUP BY d_year, p_brand1
ORDER BY d_year, p_brand1;
