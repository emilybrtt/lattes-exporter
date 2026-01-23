# Backend – Lattes Exporter

Serviço Flask responsável por ingerir datasets do Lattes, armazená-los via SQLAlchemy (SQLite por padrão ou Postgres via `DATABASE_URL`) e gerar artefatos (DOCX/PDF/JSON) para cada docente.

---

## Estrutura
- `app.py` – aplicação Flask/CORS com todos os endpoints REST e cache invalidation.
- `backend/core/config.py` – normaliza variáveis de ambiente, caminhos e cria o engine SQLAlchemy.
- `backend/core/database.py` – ingestão de planilhas, helpers de upload manual e persistência de fotos (com `store_faculty_photo`).
- `backend/services/automation.py` – consolidação de dados, geração de artefatos e cache TTL configurável.
- `backend/api/models.py` – utilidades/aliases para tipagem (quando aplicável).

Banco SQLite padrão: `data/lattes.sqlite3` (configurável via `LATTES_SQLITE_PATH`).

## Variáveis de Ambiente
- `DATABASE_URL` ou `SERVICE_URI` – substituem o SQLite por outra base suportada (ex.: `postgresql+psycopg://user:pass@host/db`).
- `LATTES_SQLITE_PATH` – caminho alternativo para o arquivo SQLite quando não há URL externa.
- `AUTOMATION_CACHE_TTL` – tempo (em segundos) de cache para `/summary` e perfis; `0` desliga o cache.

---

## Endpoints
| Método | Rota | Descrição |
|--------|------|-----------|
| GET    | `/summary` | Lista paginada com campos básicos (`page`, `per_page`, `allocated_only`, `accreditation[]`). |
| GET    | `/<id>` | Retorna o perfil completo (JSON) do docente, incluindo metadados da foto. |
| POST   | `/export` | Gera artefato DOCX/PDF (`format`, `include_photo`) para o docente informado (`id` ou `faculty_id`). |
| POST   | `/faculty/<id>/photo` | Atualiza a foto do docente (`photo` em multipart; aceita PNG/JPEG/WebP até 5 MB). |
| GET    | `/faculty/<id>/photo` | Baixa a foto armazenada, respeitando o mime type. |
| GET    | `/artifacts/<path>` | Download seguro para arquivos gerados. |
| POST   | `/tables/<table_key>/upload` | Atualiza/mescla uma tabela a partir de CSV/XLSX enviado em `file`. |
| POST   | `/automation/run` | Executa geração em lote por acreditação (opcionalmente lista de IDs). |
| GET    | `/automation/status` | Lista diretórios/acreditações já exportadas. |

### Upload de tabelas (`/tables/<table_key>/upload`)
- `table_key` aceita tanto o nome da tabela (`base_de_dados_docente`) quanto alias (`alocacao`).
- Formatos aceitos: CSV (`sep` autodetectado) e XLSX.
- As colunas precisam casar exatamente com as do dataset oficial (o arquivo base ou a tabela já existente); envios com colunas faltantes/extras são recusados.
- As linhas são mescladas com o conteúdo já existente:
  - Linhas duplicadas (idênticas) são coalescidas mantendo a versão mais recente.
  - Demais tabelas não são afetadas.
- A recriação da tabela ocorre dentro de uma transação; em caso de erro, é feito rollback completo.
- Exemplo cURL:
  ```bash
  curl -F "file=@data/base-de-dados-docente.csv" \
       http://localhost:5000/tables/base_de_dados_docente/upload
  ```

### Fotos de docentes (`/faculty/<id>/photo`)
- Envie o campo `photo` em multipart/form-data; formatos suportados: `image/png`, `image/jpeg`, `image/webp` (até 5 MB).
- Em bancos não SQLite, as imagens são armazenadas em colunas `BYTEA` compatíveis com Postgres.
- O JSON do docente indica `photo.available` e inclui URL pública quando a imagem existir.
- Exemplo cURL:
  ```bash
  curl -F "photo=@/caminho/foto.png" \
       http://localhost:5000/faculty/123/photo
  ```

---

## Scripts Úteis
- `python app.py` – inicia o servidor.
- `python -m backend.core.database` – (re)inicializa o banco a partir dos CSVs padrão.
- `python -m backend.services.automation --accreditation AACSB` – gera DOCX/JSON para uma acreditação inteira.

Logs ficam no stdout com nível `INFO`.

---

## Dependências Principais
- Flask 3 + flask-cors.
- SQLAlchemy 2 (com psycopg para Postgres, sqlite embutido por padrão).
- pandas (ingestão CSV/XLSX com engine openpyxl).
- python-docx para montagem dos currículos.
- Pillow (PIL) para tratamento da foto nos DOCX e API.
- python-dotenv para carregar `.env` automaticamente.

Instalar tudo com:
```bash
pip install -r requirements.txt
```

---

## Boas Práticas
- Sempre validar se o arquivo de upload possui cabeçalho; uploads vazios retornam 400.
- Para datasets de alocação, garanta que os nomes das disciplinas e docentes coincidam com a tabela base (case-insensitive, sem acentos).
- Utilize variáveis de ambiente para customizar caminhos (`LATTES_SQLITE_PATH`).
- Fotos maiores que 5 MB ou fora dos formatos aceitos retornam 400; gere thumbs no frontend antes de enviar.
- Ao trocar de base (`DATABASE_URL`), rode `python -m backend.core.database` para recriar tabelas a partir dos CSVs.
