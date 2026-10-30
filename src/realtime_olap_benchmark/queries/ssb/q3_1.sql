-- SSB Q3.1: revenue by customer and supplier nation, Asia, 1992 to 1997
SELECT c_nation, s_nation, d_year, sum(lo_revenue) AS revenue
FROM customer, lineorder, supplier, dates
WHERE lo_custkey = c_custkey
  AND lo_suppkey = s_suppkey
  AND lo_orderdate = d_datekey
  AND c_region = 'ASIA'
  AND s_region = 'ASIA'
  AND d_year >= 1992 AND d_year <= 1997
GROUP BY c_nation, s_nation, d_year
ORDER BY d_year ASC, revenue DESC;
