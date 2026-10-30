-- SSB Q1.1: revenue gained by removing small discounts, one year
SELECT sum(lo_extendedprice * lo_discount) AS revenue
FROM lineorder, dates
WHERE lo_orderdate = d_datekey
  AND d_year = 1993
  AND lo_discount BETWEEN 1 AND 3
  AND lo_quantity < 25;
