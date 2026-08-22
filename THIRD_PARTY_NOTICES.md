# Third-Party Notices

This project uses third-party software packages. The following notices are provided
in accordance with the respective licenses.

## Apache Airflow

- **Website:** https://airflow.apache.org
- **License:** Apache License 2.0
- **Usage:** Workflow orchestration (webserver, scheduler, init)
- **Image:** `apache/airflow:2.9.3-python3.11`

## PostgreSQL

- **Website:** https://www.postgresql.org
- **License:** PostgreSQL License (similar to MIT/BSD)
- **Usage:** Primary relational database
- **Image:** `postgres:16-alpine`

## MinIO

- **Website:** https://min.io
- **License:** GNU Affero General Public License v3.0 (AGPL-3.0)
- **Usage:** S3-compatible object storage for parquet data lake
- **Image:** `minio/minio:RELEASE.2024-09-22T00-33-43Z`

> **Note:** MinIO uses AGPL-3.0. If you modify MinIO source code, you must release
> those modifications under AGPL-3.0. Using MinIO as a service (without modification)
> does not trigger this obligation.

## Python Dependencies (requirements-airflow.txt)

| Package | License | Description |
|---------|---------|-------------|
| python-dotenv | BSD-3-Clause | Load .env files |
| google-auth | Apache-2.0 | Google authentication |
| google-api-python-client | Apache-2.0 | Google API client |
| gspread | MIT | Google Sheets API wrapper |
| openpyxl | MIT | Excel file reader/writer |
| pandas | BSD-3-Clause | Data manipulation |
| psycopg2-binary | LGPL-2.1+ | PostgreSQL adapter |
| SQLAlchemy | MIT | SQL toolkit and ORM |
| requests | Apache-2.0 | HTTP client library |
| pyarrow | Apache-2.0 | Apache Arrow / Parquet support |
| minio | Apache-2.0 | MinIO S3-compatible client |
| oracledb | Apache-2.0 | Oracle database driver |

## System Packages (Dockerfile.airflow)

| Package | License | Description |
|---------|---------|-------------|
| build-essential | GPL-2.0+ (collection) | Compilers and make |
| libpq-dev | PostgreSQL License | PostgreSQL development headers |

## Licenses

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

MinIO is licensed under AGPL-3.0. For details, see:
https://www.gnu.org/licenses/agpl-3.0.html

### GNU Lesser General Public License v2.1+

psycopg2 is licensed under LGPL-2.1+ (or later). For details, see:
https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html

---

**Generated:** 2026-08-22
