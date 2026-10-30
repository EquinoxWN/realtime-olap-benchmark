### SSB (scale factor 0.1), median milliseconds

| Query | duckdb cold | duckdb hot |
|---|---:|---:|
| Q1.1 | 9.7 | 6.5 |
| Q1.2 | 31.7 | 20.5 |
| Q1.3 | 16.9 | 11.6 |
| Q2.1 | 49.8 | 43.3 |
| Q2.2 | 75.6 | 44.7 |
| Q2.3 | 51.6 | 19.0 |
| Q3.1 | 148 | 60.2 |
| Q3.2 | 20.8 | 10.1 |
| Q3.3 | 11.0 | 8.7 |
| Q3.4 | 9.9 | 7.2 |
| Q4.1 | 20.2 | 12.9 |
| Q4.2 | 20.0 | 14.1 |
| Q4.3 | 16.2 | 13.0 |
| geometric mean | **25.8** | **16.2** |

- **duckdb** v2.0.0 (embedded in the harness process (Python package)); threads 4; 3 cold, 1 warm-up, 5 hot runs; cold = close and reopen the database file (empties DuckDB's buffer pool); load 0.7 s

### TPCH (scale factor 0.1), median milliseconds

| Query | duckdb cold | duckdb hot |
|---|---:|---:|
| Q01 | 15.3 | 10.6 |
| Q03 | 16.2 | 11.3 |
| Q05 | 18.6 | 12.9 |
| Q06 | 7.7 | 6.0 |
| Q10 | 29.7 | 23.5 |
| Q12 | 18.0 | 10.9 |
| Q14 | 10.2 | 8.2 |
| Q18 | 21.8 | 14.6 |
| geometric mean | **16.0** | **11.4** |

- **duckdb** v2.0.0 (embedded in the harness process (Python package)); threads 4; 3 cold, 1 warm-up, 5 hot runs; cold = close and reopen the database file (empties DuckDB's buffer pool); load 1.6 s
