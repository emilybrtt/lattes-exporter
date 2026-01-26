# Backend – CV Exporter
Serviço Flask responsável por ingerir datasets do Lattes, persistir dados via SQLAlchemy (SQLite por padrão) e gerar artefatos DOCX, PDF e JSON para cada docente.

---

## Visão rápida
- [../app.py](../app.py) fornece as rotas REST (lista, exportação, upload e automação).
- [core/config.py](core/config.py) centraliza caminhos, variáveis de ambiente e engine.
- [core/database.py](core/database.py) normaliza CSV/XLSX e recria tabelas com segurança transacional.
- [services/automation.py](services/automation.py) consolida dados, gera documentos e aplica cache TTL.
- Tabelas extras e tipos utilitários estão em [api/models.py](api/models.py).

Banco padrão: [../data/lattes.sqlite3](../data/lattes.sqlite3). Use `LATTES_SQLITE_PATH` para sobrescrever.

---

## Variáveis de ambiente
- `DATABASE_URL` ou `SERVICE_URI` — utiliza Postgres (psycopg) ou outro banco suportado pelo SQLAlchemy.
- `LATTES_SQLITE_PATH` — aponta para arquivo SQLite customizado.
- `AUTOMATION_CACHE_TTL` — tempo em segundos do cache de `/summary` e perfis (0 desliga).

Defina-as em um `.env` na raiz e o módulo [core/config.py](core/config.py) tratará automaticamente.

---

## Endpoints principais
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/summary` | Lista paginada com filtros de alocação e acreditação. |
| GET | `/<id>` | Retorna o perfil completo com foto e produções. |
| POST | `/export` | Gera DOCX ou PDF para um docente (`format`, `include_photo`). |
| POST | `/faculty/<id>/photo` | Recebe foto do docente (PNG/JPEG/WebP até 5 MB). |
| GET | `/faculty/<id>/photo` | Download da foto armazenada. |
| GET | `/artifacts/<path>` | Download seguro dos arquivos gerados. |
| POST | `/tables/<table_key>/upload` | Substitui tabela a partir de CSV/XLSX enviado via multipart. |
| POST | `/automation/run` | Exporta todos os docentes de uma acreditação específica. |
| GET | `/automation/status` | Lista diretórios gerados no output. |

### Upload de tabelas (`/tables/<table_key>/upload`)
- Aceita nomes de tabela ou aliases definidos em `CSV_SPECS`.
- Formatos suportados: CSV (delimitadores `,`, `;`, `\t`, `|` autodetectados) e XLSX.
- Estrutura de colunas é validada; arquivos com cabeçalho divergente retornam 400.
- Operação executa dentro de transação: em caso de erro, nada é gravado.

Exemplo cURL:
```bash
curl -F "file=@data/base-de-dados-docente.csv" \
  http://localhost:5000/tables/base_de_dados_docente/upload
```

### Upload de fotos (`/faculty/<id>/photo`)
- Envie multipart com campo `photo`.
- Formatos: `image/png`, `image/jpeg`, `image/webp`.
- Resposta inclui metadados e invalida automaticamente o cache em memória.

Exemplo cURL:
```bash
curl -F "photo=@/caminho/foto.png" \
  http://localhost:5000/faculty/123/photo
```

---

## Scripts úteis
- `python app.py` — inicia a API com CORS habilitado.
- `python -m backend.core.database` — recria tabelas a partir das planilhas padrão.
- `python -m backend.services.automation --accreditation AACSB` — gera DOCX e JSON para todos os docentes com AACSB.

Logs são enviados para stdout com nível `INFO` por padrão.

---

## Dependências principais
- Flask 3 e flask-cors para as rotas REST.
- SQLAlchemy 2 + pandas para ingestão e persistência tabular.
- python-docx e Pillow para compor o DOCX com fotos.
- python-dotenv para carregar configurações a partir do `.env`.

Instale tudo executando:
```bash
pip install -r requirements.txt
```

---

## Boas práticas
- Verifique cabeçalho e delimitador antes de enviar planilhas para o endpoint `/tables/...`.
- Ao alterar a origem do banco (Postgres/SQLite), rode novamente `backend.core.database` para popular dados.
- Limite fotos a 5 MB; considere gerar miniaturas no frontend antes do upload.
- Utilize `AUTOMATION_CACHE_TTL=0` em ambientes de desenvolvimento quando precisar refletir mudanças imediatamente.
