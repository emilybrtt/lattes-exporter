# Lattes Exporter

Pipeline completo para gerar pacotes de currículo (DOCX + JSON) a partir dos dados consolidados dos docentes. O projeto combina um backend Flask/SQLite e um frontend React Router com foco em atualização rápida de datasets e exportação em lote.

---

## Visão Geral
- Banco SQLite construído a partir de planilhas CSV/XLSX do Lattes.
- Backend Flask expõe endpoints REST para listar docentes, atualizar tabelas manualmente e gerar artefatos.
- Frontend em React Router (TypeScript + shadcn/ui) oferece painel com filtros avançados, busca textual e exportação em lote.

---

## Arquitetura

### Backend (Python 3.11)
- [backend/core/config.py](backend/core/config.py):
  - Centraliza caminhos de dados/exports e criação do engine SQLAlchemy.
  - Aceita `.env` com `DATABASE_URL`/`SERVICE_URI` (Postgres ou SQLite) e `LATTES_SQLITE_PATH`.
- [backend/core/database.py](backend/core/database.py):
  - Mapeia arquivos suportados via `CSV_SPECS`, incluindo tabelas de alocação.
  - Disponibiliza `reload_table_from_upload`, que aceita CSV ou XLSX (delimitadores automáticos) e recria a tabela conforme o banco ativo.
- [backend/services/automation.py](backend/services/automation.py):
  - Consolida dados dos docentes (dados básicos, experiências, produções e creditações).
  - Gera documentos DOCX a partir de templates (python-docx), persiste fotos opcionais e registra metadados dos artefatos.
- [app.py](app.py): endpoints principais:
  - `GET /summary` – lista paginada de docentes (`page`, `per_page`, `allocated_only`, `accreditation[]`).
  - `GET /<id>` – perfil completo de um docente (com URL da foto quando existir).
  - `POST /export` – gera DOCX/PDF (`format`, `include_photo`) e retorna metadados com URLs de download.
  - `POST /faculty/<id>/photo` / `GET /faculty/<id>/photo` – upload e download seguros das fotos dos docentes (PNG/JPEG/WebP).
  - `POST /tables/<table_key>/upload` – upload manual de planilhas (`file` em multipart) para qualquer tabela cadastrada.
  - `GET /artifacts/<path>` – download seguro do artefato gerado.
  - `POST /automation/run` / `GET /automation/status` – execução em lote por acreditação.

### Frontend (React Router + Vite)
- Tudo em [frontend/app](frontend/app) com JSX server-first via `react-router@7`.
- Componentes estilizados com shadcn/ui + Tailwind.
- [frontend/app/components/export-panel.tsx](frontend/app/components/export-panel.tsx):
  - Busca textual (nome, email, área, unidade), filtros por área/unidade/acreditação, modos grid/tabela.
  - Seleção em lote com exportação DOCX/PDF e resumo de downloads.
- [frontend/app/routes/datasets.upload.tsx](frontend/app/routes/datasets.upload.tsx):
  - Página para carregar planilhas (CSV/XLSX) via API `/tables/<table_key>/upload` com feedback visual e coluna preview.
- [frontend/app/lib/api.ts](frontend/app/lib/api.ts): cliente HTTP tipado (fetch) com normalização de payloads.

---

## Fontes de Dados Suportadas
- [data/base-de-dados-docente.csv](data/base-de-dados-docente.csv)
- [data/docentes-experiencia-profissional.csv](data/docentes-experiencia-profissional.csv)
- [data/producao_docentes_detalhado.csv](data/producao_docentes_detalhado.csv) (ignora a primeira linha de metadados)
- [data/Alocacao_2026 1_Rel_Detalhe.csv](data/Alocacao_2026%201_Rel_Detalhe.csv) (aceita também uploads como alocacao_2026_1_reldetalhe.csv e alocacao-2026-1-reldetalhe.csv)
- [data/alocacao-26-1.csv](data/alocacao-26-1.csv) (aceita também uploads como alocacao_26_1.csv)

Qualquer upload manual aceita CSV com delimitador `,`, `;`, `\t`, `|` ou XLSX (`openpyxl`).

---

## Configuração do Ambiente

### Backend
1. Ative o ambiente virtual
   ```powershell
   env\Scripts\Activate.ps1
   ```
2. Instale as dependências
   ```bash
   pip install -r requirements.txt
   ```
3. Execute o servidor Flask
   ```bash
   python app.py
   ```
   O backend fica em `http://localhost:5000`.

  Opcional: crie um arquivo `.env` na raiz para configurar banco e cache. Exemplos:

  ```dotenv
  DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dbname
  LATTES_SQLITE_PATH=C:/dados/lattes.sqlite3
  AUTOMATION_CACHE_TTL=300
  ```

  - `DATABASE_URL` ou `SERVICE_URI` ativam Postgres (ou outro banco suportado pelo SQLAlchemy).
  - O fallback é SQLite em `data/lattes.sqlite3`; use `LATTES_SQLITE_PATH` para apontar outro arquivo.
  - `AUTOMATION_CACHE_TTL` controla (em segundos) o cache de `/summary` e perfis; defina `0` para desligar.

### Frontend
1. Instale dependências
   ```bash
   cd frontend
   npm install
   ```
2. Inicie o modo desenvolvimento
   ```bash
   npm run dev
   ```
   A interface abre em `http://localhost:5173/app` (rotas internas `/app` e `/datasets/upload`).

Variável opcional: defina `VITE_API_BASE_URL` para apontar para outro backend.

---

## Fluxos Principais
1. **Atualizar dados via UI**: abra `/datasets/upload`, envie novos CSV/XLSX para cada tabela, verifique contagem/colunas retornadas.
2. **Navegar no painel**: em `/app` utilize busca e filtros para localizar docentes. Use “Selecionar todos” e exporte em DOCX ou PDF.
3. **Gerenciar fotos**: envie imagens via `POST /faculty/<id>/photo` (PNG/JPEG/WebP até 5 MB); visualize em `/faculty/<id>/photo` ou diretamente no painel.
4. **Downloads**: após exportar, links ficam disponíveis tanto no modal quanto via `/artifacts/<path>`.

CLI (automatização):
- `python -m backend.services.automation --accreditation AACSB`
- `python -m backend.services.automation --accreditation AACSB --faculty 123 456`

---

## Notas Técnicas
- Logs configurados com `logging.basicConfig(level=logging.INFO)`.
- Sanitização de colunas no SQLite garante nomes `snake_case` sem caracteres especiais.
- Uploads derrubam e recriam a tabela alvo dentro de uma transação SQLite.
- Busca do frontend normaliza texto para remover acentos antes de comparar.
- Exportação PDF reutiliza o DOCX gerado e converte via automação (python-docx + pipeline de exportação).

---

## Solução de Problemas
- **Nenhum docente exibido**: confirme `/summary` no backend e se as planilhas de alocação foram atualizadas (nomes devem coincidir).
- **Erro no upload**: resposta contém `error`. Verifique se o arquivo está no formato CSV/XLSX e se o cabeçalho não está vazio.
- **Artefato não abre**: confirme que `backend/exports/output/<accreditation>/` contém o arquivo e que `/artifacts/…` retorna 200.
- **Falha de conexão com o banco**: revise `DATABASE_URL`/`SERVICE_URI` no `.env` e confirme que a URL segue o padrão `postgresql+psycopg://` (ou remova para voltar ao SQLite padrão).

---

## Próximos Passos
- Cobrir `/tables/<table_key>/upload` e `/summary` com testes automatizados.
- Adicionar autenticação (JWT/Keycloak) para restringir uploads e exportações.
- Publicar documentação OpenAPI do backend.
