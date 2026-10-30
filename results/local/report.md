### SSB (scale factor 0.1), median milliseconds

| Query | duckdb cold | duckdb hot |
|---|---:|---:|
| Q1.1 | 37.7 | 22.6 |
| Q1.2 | 37.6 | 28.7 |
| Q1.3 | 35.7 | 21.7 |
| Q2.1 | 60.0 | 47.5 |
| Q2.2 | 43.0 | 34.2 |
| Q2.3 | 34.6 | 28.3 |
| Q3.1 | 68.3 | 41.1 |
| Q3.2 | 49.4 | 60.6 |
| Q3.3 | 64.3 | 33.3 |
| Q3.4 | 36.8 | 29.3 |
| Q4.1 | 57.4 | 35.0 |
| Q4.2 | 31.8 | 16.7 |
| Q4.3 | 19.9 | 27.5 |
| geometric mean | **42.1** | **31.1** |

- **duckdb** v2.0.0 (embedded in the harness process (Python package)); threads 20; 3 cold, 1 warm-up, 5 hot runs; cold = close and reopen the database file (empties DuckDB's buffer pool); load 2.8 s

### TPCH (scale factor 0.1), median milliseconds

| Query | duckdb cold | duckdb hot |
|---|---:|---:|
| Q01 | 86.9 | 62.1 |
| Q03 | 61.7 | 54.8 |
| Q05 | 105 | 50.8 |
| Q06 | 15.2 | 8.0 |
| Q10 | 55.0 | 59.8 |
| Q12 | 37.7 | 24.2 |
| Q14 | 18.0 | 13.8 |
| Q18 | 77.4 | 88.9 |
| geometric mean | **47.2** | **35.4** |

- **duckdb** v2.0.0 (embedded in the harness process (Python package)); threads 20; 3 cold, 1 warm-up, 5 hot runs; cold = close and reopen the database file (empties DuckDB's buffer pool); load 5.7 s
