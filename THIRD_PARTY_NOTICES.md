# Third-Party Notices

This project uses third-party software packages. The following notices are provided
in accordance with the respective licenses. **This document is for informational
purposes only and does not constitute legal advice.** Consult a qualified attorney
for guidance on license compliance in your specific context.

## Component Notices

### Apache Airflow

- **Website:** https://airflow.apache.org
- **Repository:** https://github.com/apache/airflow
- **License:** Apache License 2.0
- **License Text:** https://www.apache.org/licenses/LICENSE-2.0
- **Usage:** Workflow orchestration (webserver, scheduler, init)
- **Image:** `apache/airflow:2.9.3-python3.11`

### PostgreSQL

- **Website:** https://www.postgresql.org
- **Repository:** https://github.com/postgres/postgres
- **License:** PostgreSQL License (liberal, similar to MIT/BSD)
- **License Text:** https://www.postgresql.org/about/licence/
- **Usage:** Primary relational database (5 databases: elt, bronze, silver, gold, airflow)
- **Image:** `postgres:16-alpine`

### MinIO (Server)

- **Website:** https://min.io
- **Repository:** https://github.com/minio/minio
- **License:** GNU Affero General Public License v3.0 (AGPL-3.0)
- **License Text:** https://www.gnu.org/licenses/agpl-3.0.html
- **Usage:** S3-compatible object storage for parquet data lake
- **Image:** `minio/minio:RELEASE.2024-09-22T00-33-43Z`

> **AGPL-3.0 Advisory:**
> MinIO's AGPL-3.0 license requires that if you **modify** MinIO and make the
> modified version available to users over a network, you must offer the
> complete corresponding source code under AGPL-3.0 terms. Running
> **unmodified** MinIO as an internal service (without distributing modified
> MinIO binaries or source) does **not** trigger this obligation. This project
> does not modify MinIO; it is used as a stock Docker image only. However,
> AGPL compliance depends on your specific deployment and usage — consult
> legal counsel if you are unsure.

### MinIO SDK (minio-py)

- **Website:** https://min.io
- **Repository:** https://github.com/minio/minio-py
- **License:** Apache License 2.0
- **License Text:** https://github.com/minio/minio-py/blob/master/LICENSE
- **Usage:** Python client for MinIO S3-compatible API (upload/download parquet objects)

### SQLAlchemy

- **Website:** https://www.sqlalchemy.org
- **Repository:** https://github.com/sqlalchemy/sqlalchemy
- **License:** MIT License
- **License Text:** https://github.com/sqlalchemy/sqlalchemy/blob/main/LICENSE
- **Usage:** Database connectivity via connection pooling (PostgreSQL, Oracle)

### pandas

- **Website:** https://pandas.pydata.org
- **Repository:** https://github.com/pandas-dev/pandas
- **License:** BSD-3-Clause
- **License Text:** https://github.com/pandas-dev/pandas/blob/main/LICENSE
- **Usage:** DataFrame manipulation for all extractors and transforms

### PyArrow

- **Website:** https://arrow.apache.org
- **Repository:** https://github.com/apache/arrow
- **License:** Apache License 2.0
- **License Text:** https://github.com/apache/arrow/blob/main/LICENSE.txt
- **Usage:** Parquet file format support for MinIO datalake

### OpenPyXL

- **Website:** https://openpyxl.readthedocs.io
- **Repository:** https://github.com/openpyxl/openpyxl
- **License:** MIT License
- **License Text:** https://openpyxl.readthedocs.io/en/stable/license.html
- **Usage:** Excel (.xlsx) file reading/writing

### Requests

- **Website:** https://requests.readthedocs.io
- **Repository:** https://github.com/psf/requests
- **License:** Apache License 2.0
- **License Text:** https://github.com/psf/requests/blob/main/LICENSE
- **Usage:** HTTP client for REST API extraction and CSV downloads

### psycopg2-binary

- **Website:** https://www.psycopg.org
- **Repository:** https://github.com/psycopg/psycopg2
- **License:** LGPL-2.1+ (or later)
- **License Text:** https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html
- **Usage:** PostgreSQL adapter for Python (native, via libpq)

### python-oracledb

- **Website:** https://oracle.github.io/python-oracledb
- **Repository:** https://github.com/oracle/python-oracledb
- **License:** Apache License 2.0
- **License Text:** https://github.com/oracle/python-oracledb/blob/main/LICENSE.txt
- **Usage:** Oracle database driver (Thin mode, no Oracle Client required)

### google-api-python-client

- **Website:** https://github.com/googleapis/google-api-python-client
- **Repository:** https://github.com/googleapis/google-api-python-client
- **License:** Apache License 2.0
- **License Text:** https://github.com/googleapis/google-api-python-client/blob/main/LICENSE
- **Usage:** Google Sheets API v4 client

### gspread

- **Website:** https://github.com/burnash/gspread
- **Repository:** https://github.com/burnash/gspread
- **License:** MIT License
- **License Text:** https://github.com/burnash/gspread/blob/master/LICENSE
- **Usage:** Google Sheets API wrapper (simplified interface)

### JupyterHub / JupyterLab

- **Website:** https://jupyter.org
- **Repository:** https://github.com/jupyter/jupyter_server
- **License:** BSD-3-Clause
- **License Text:** https://github.com/jupyter/jupyter_server/blob/main/LICENSE
- **Usage:** JupyterLab interactive IDE for Data Lab notebooks
- **Image:** `jupyter/pyspark-notebook:python-3.11`

### PySpark (Apache Spark)

- **Website:** https://spark.apache.org
- **Repository:** https://github.com/apache/spark
- **License:** Apache License 2.0
- **License Text:** https://www.apache.org/licenses/LICENSE-2.0
- **Usage:** Distributed data processing (Data Lab notebooks 10-12)

### NumPy

- **Website:** https://numpy.org
- **Repository:** https://github.com/numpy/numpy
- **License:** BSD-3-Clause
- **License Text:** https://github.com/numpy/numpy/blob/main/LICENSE.txt
- **Usage:** Numerical arrays (Data Lab notebook 02)

### Polars

- **Website:** https://pola.rs
- **Repository:** https://github.com/pola-rs/polars
- **License:** MIT License
- **License Text:** https://github.com/pola-rs/polars/blob/main/LICENSE.txt
- **Usage:** High-performance DataFrame library (Data Lab notebook 04)

### DuckDB

- **Website:** https://duckdb.org
- **Repository:** https://github.com/duckdb/duckdb
- **License:** MIT License
- **License Text:** https://github.com/duckdb/duckdb/blob/main/LICENSE
- **Usage:** In-process SQL analytics engine (Data Lab notebook 04)

### Matplotlib

- **Website:** https://matplotlib.org
- **Repository:** https://github.com/matplotlib/matplotlib
- **License:** PSF-based (Matplotlib License)
- **License Text:** https://github.com/matplotlib/matplotlib/blob/main/LICENSE
- **Usage:** 2D plotting library (Data Lab notebook 08)

### Seaborn

- **Website:** https://seaborn.pydata.org
- **Repository:** https://github.com/mwaskom/seaborn
- **License:** BSD-3-Clause
- **License Text:** https://github.com/mwaskom/seaborn/blob/master/LICENSE
- **Usage:** Statistical data visualization (Data Lab notebook 08)

### Plotly

- **Website:** https://plotly.com
- **Repository:** https://github.com/plotly/plotly.py
- **License:** MIT License
- **License Text:** https://github.com/plotly/plotly.py/blob/master/LICENSE
- **Usage:** Interactive visualization (Data Lab notebook 08)

### scikit-learn

- **Website:** https://scikit-learn.org
- **Repository:** https://github.com/scikit-learn/scikit-learn
- **License:** BSD-3-Clause
- **License Text:** https://github.com/scikit-learn/scikit-learn/blob/main/LICENSE
- **Usage:** Machine learning (Data Lab notebook 09)

### python-dotenv

- **Website:** https://github.com/theskumar/python-dotenv
- **Repository:** https://github.com/theskumar/python-dotenv
- **License:** BSD-3-Clause
- **License Text:** https://github.com/theskumar/python-dotenv/blob/main/LICENSE
- **Usage:** Load environment variables from .env files

## System Packages (Dockerfile.airflow)

| Package | License | Description |
|---------|---------|-------------|
| build-essential | GPL-2.0+ (collection) | Compilers and make |
| libpq-dev | PostgreSQL License | PostgreSQL development headers |

## License Summary

| License | Components |
|---------|-----------|
| Apache 2.0 | Airflow, PyArrow, Requests, python-oracledb, minio-py, google-api-python-client, PySpark |
| MIT | SQLAlchemy, OpenPyXL, gspread, Polars, DuckDB, Plotly |
| BSD-3-Clause | pandas, python-dotenv, JupyterHub/JupyterLab, NumPy, Seaborn, scikit-learn |
| LGPL-2.1+ | psycopg2 |
| PostgreSQL License | PostgreSQL |
| AGPL-3.0 | MinIO Server |
| PSF-based | Matplotlib |

## Full License Texts

### Apache License 2.0

```
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

### MIT License

```
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### GNU Affero General Public License v3.0

MinIO Server is licensed under AGPL-3.0. For the full license text, see:
https://www.gnu.org/licenses/agpl-3.0.html

### GNU Lesser General Public License v2.1+

psycopg2 is licensed under LGPL-2.1+ (or later). For the full license text, see:
https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html

---

**Disclaimer:** This document is provided for informational purposes only. It is
not legal advice and should not be relied upon as such. License obligations depend
on how each component is used, modified, and distributed in your specific context.
Consult a qualified attorney for guidance on open-source license compliance.

**Generated:** 2026-08-22
