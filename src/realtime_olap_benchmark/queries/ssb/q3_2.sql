-- SSB Q3.2: revenue by customer and supplier city, United States, 1992 to 1997
SELECT c_city, s_city, d_year, sum(lo_revenue) AS revenue
FROM customer, lineorder, supplier, dates
WHERE lo_custkey = c_custkey
  AND lo_suppkey = s_suppkey
  AND lo_orderdate = d_datekey
  AND c_nation = 'UNITED STATES'
  AND s_nation = 'UNITED STATES'
  AND d_year >= 1992 AND d_year <= 1997
GROUP BY c_city, s_city, d_year
ORDER BY d_year ASC, revenue DESC;
