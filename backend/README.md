# Backend – Lattes Exporter

Serviço Flask responsável por ingerir datasets do Lattes, armazená-los em SQLite e gerar artefatos (DOCX/PDF/JSON) para cada docente.

---

## Estrutura
- `app.py` – aplicação Flask/CORS com todos os endpoints REST.
- `backend/core/database.py` – ingestão de planilhas e helpers para uploads manuais.
- `backend/services/automation.py` – consolidação de dados e geração dos artefatos.
- `backend/api/models.py` – utilidades/aliases para tipagem (quando aplicável).

Banco SQLite padrão: `data/lattes.sqlite3` (configurável via `LATTES_SQLITE_PATH`).

---

## Endpoints
| Método | Rota | Descrição |
|--------|------|-----------|
| GET    | `/summary` | Lista paginada com campos básicos (id, nome, área, unidade, creditações). |
| GET    | `/<id>` | Retorna o perfil completo (JSON) do docente. |
| POST   | `/export` | Gera artefato DOCX/PDF para o docente informado (`id` ou `faculty_id`). |
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

---

## Scripts Úteis
- `python app.py` – inicia o servidor.
- `python -m backend.core.database` – (re)inicializa o banco a partir dos CSVs padrão.
- `python -m backend.services.automation --accreditation AACSB` – gera DOCX/JSON para uma acreditação inteira.
- `python -m unittest backend.tests.test_database_upload` – executa os testes automatizados de upload de tabelas.

Logs ficam no stdout com nível `INFO`.

---

## Dependências Principais
- Flask 3 + flask-cors.
- pandas (ingestão CSV/XLSX com engine openpyxl).
- python-docx para montagem dos currículos.

Instalar tudo com:
```bash
pip install -r requirements.txt
```

---

## Boas Práticas
- Sempre validar se o arquivo de upload possui cabeçalho; uploads vazios retornam 400.
- Para datasets de alocação, garanta que os nomes das disciplinas e docentes coincidam com a tabela base (case-insensitive, sem acentos).
- Utilize variáveis de ambiente para customizar caminhos (`LATTES_SQLITE_PATH`).
