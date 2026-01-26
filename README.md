# CV Exporter

Pipeline completo para gerar currículos DOCX, PDF e JSON a partir de dados consolidados do corpo docente. O repositório combina backend Flask/SQLAlchemy e frontend React Router para acelerar a atualização de datasets e a exportação em lote.

---

## Visão geral
- Banco local SQLite inicializado a partir de planilhas CSV/XLSX oriundas do Lattes.
- Backend Flask com endpoints REST para listagem, upload de tabelas, exportação e gestão de fotos.
- Frontend em React Router (TypeScript + Tailwind + shadcn/ui) que oferece filtros avançados, busca, exportação em massa e upload guiado.

---

## Estrutura do repositório
- [app.py](app.py) — API Flask com rotas de resumo, exportação, upload e automação.
- [backend](backend) — núcleo de ingestão, configurações e serviço de automação de CVs.
- [frontend](frontend) — painel web para operadores acompanharem filtros, uploads e resultados.
- [data](data) — planilhas de exemplo utilizadas para popular o banco local.

Consulte [backend/README.md](backend/README.md) e [frontend/README.md](frontend/README.md) para guias específicos.

---

## Pré-requisitos
- Python 3.11+ com virtualenv disponível.
- Node.js 20 LTS e npm 10+ para o frontend.
- Microsoft Word e pywin32 instalados (apenas se a exportação em PDF for necessária no Windows).

---

## Passo a passo rápido
1. Criar e ativar o ambiente virtual Python:
  ```powershell
  python -m venv env
  env\Scripts\Activate.ps1
  ```
2. Instalar dependências do backend:
  ```bash
  pip install -r requirements.txt
  ```
3. Inicializar o banco com as planilhas padrão (opcional):
  ```bash
  python -m backend.core.database
  ```
4. Rodar o servidor Flask em <http://localhost:5000>:
  ```bash
  python app.py
  ```
5. Instalar e subir o frontend em outra janela:
  ```bash
  cd frontend
  npm install
  npm run dev
  ```

Variáveis de ambiente recomendadas (arquivo `.env` na raiz):
```dotenv
DATABASE_URL=postgresql+psycopg://usuario:senha@host:5432/banco
LATTES_SQLITE_PATH=C:/dados/lattes.sqlite3
AUTOMATION_CACHE_TTL=300
```
No frontend (`frontend/.env`), utilize `VITE_API_BASE_URL` para apontar para um backend remoto.

---

## Principais módulos do backend
- [backend/core/config.py](backend/core/config.py) — resolve caminhos, carrega `.env` e monta o engine SQLAlchemy com cache.
- [backend/core/database.py](backend/core/database.py) — normaliza colunas, aceita uploads CSV/XLSX e recria tabelas dentro de transação.
- [backend/services/automation.py](backend/services/automation.py) — consolida dados dos docentes, monta DOCX, exporta PDFs (Windows) e gera JSON.
- [backend/api/models.py](backend/api/models.py) — dataclasses utilitárias para tipagem de docentes.

Endpoints relevantes expostos por [app.py](app.py):
- `GET /summary` — resumo paginado com filtros de acreditação e alocação.
- `GET /<id>` — perfil completo com foto e histórico.
- `POST /export` — gera artefato DOCX/PDF para um docente.
- `POST /faculty/<id>/photo` — atualiza foto (PNG/JPEG/WebP até 5 MB).
- `POST /tables/<table_key>/upload` — substitui tabelas com CSV ou XLSX.
- `POST /automation/run` — executa exportação em lote por acreditação.

---

## Principais módulos do frontend
- [frontend/app/components/export-panel.tsx](frontend/app/components/export-panel.tsx) — painel com filtros, paginação, exportação e upload de fotos.
- [frontend/app/routes/datasets.upload.tsx](frontend/app/routes/datasets.upload.tsx) — fluxo completo de upload com validação de extensões e toasts.
- [frontend/app/lib/api.ts](frontend/app/lib/api.ts) — cliente fetch com normalização e tratamento de erros.
- [frontend/app/lib/use-faculty-filters.ts](frontend/app/lib/use-faculty-filters.ts) — hook que sincroniza filtros com a URL.

---

## Fontes de dados e uploads
- [data/base-de-dados-docente.csv](data/base-de-dados-docente.csv)
- [data/docentes-experiencia-profissional.csv](data/docentes-experiencia-profissional.csv)
- [data/producao_docentes_detalhado.csv](data/producao_docentes_detalhado.csv) — ignora a primeira linha de metadados.
- [data/Alocacao_2026 1_Rel_Detalhe.csv](data/Alocacao_2026%201_Rel_Detalhe.csv)
- [data/alocacao-26-1.csv](data/alocacao-26-1.csv)

Uploads podem ser feitos via frontend (rota `/datasets/upload`) ou cURL, aceitando CSV com delimitadores `,`, `;`, `	`, `|` e arquivos XLSX.

---

## Fluxos recomendados
1. **Atualizar datasets** — usar `/datasets/upload` para enviar planilha, revisar colunas retornadas e confirmar contagem de linhas.
2. **Exportar currículos** — aplicar filtros em `/app`, selecionar docentes e gerar DOCX/PDF; links ficam disponíveis em `/artifacts/<path>`.
3. **Gerenciar fotos** — enviar imagens via endpoint ou painel, invalidando cache automaticamente.

Scripts CLI úteis:
- `python -m backend.services.automation --accreditation AACSB`
- `python -m backend.services.automation --accreditation EQUIS --faculty 123 456`

---

## Solução de problemas
- **Listagem vazia** — verifique se o banco foi inicializado (`python -m backend.core.database`) e se o backend responde em `/summary`.
- **Falha no upload** — confirme cabeçalho completo e formato do arquivo; o backend retorna mensagem detalhada em JSON.
- **PDF não gerado** — a conversão requer Windows com Word e pywin32 instalados; use `export_format=docx` como alternativa.
- **Erro de conexão** — revise variáveis `DATABASE_URL` ou `SERVICE_URI`; para SQLite, assegure que o arquivo exista e seja acessível.

---

## Próximos passos sugeridos
- Cobrir endpoints críticos com testes (`pytest`) e adicionar mocks para automatizar geração de artefatos.
- Implementar autenticação para restringir uploads e exportações.
- Publicar a especificação OpenAPI hospedada em [backend/docs/openapi.yaml](backend/docs/openapi.yaml).
