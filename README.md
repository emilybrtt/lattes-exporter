# Lattes Exporter

Pipeline completo para gerar pacotes de currículo (DOCX + JSON) a partir dos dados consolidados dos docentes, com backend em Flask/SQLite e frontend em React Router.

---

## Visão Geral
- Ingestão dos CSVs do Lattes para um banco SQLite local gerenciado pelo backend.
- Serviço Flask expõe endpoints REST para listar docentes, exportar CVs e distribuir artefatos gerados.
- Frontend React (TypeScript + shadcn/ui) oferece um painel para selecionar docentes, disparar exportações e baixar arquivos.

---

## Arquitetura

### Backend (Python 3.11)
- [backend/core/database.py](backend/core/database.py): carrega os CSVs descritos em `CSV_SPECS`, criando/atualizando `data/lattes.sqlite3`.
- [backend/services/automation.py](backend/services/automation.py): monta o perfil completo do docente, gera JSON serializado e usa python-docx para produzir o DOCX.
- [app.py](app.py): aplica Flask + CORS e expõe os endpoints HTTP abaixo:
  - `GET /` – lista todos os docentes já formatados para JSON (`{ total, result }`).
  - `GET /<id>` – retorna o perfil de um docente específico.
  - `POST /export` – dispara a geração do DOCX (já existente) e devolve metadados com `docx_url` pronto para download.
  - `GET /artifacts/<path>` – novo endpoint que disponibiliza qualquer artefato gerado de forma segura (usa `automation_service.output_root`).
  - `POST /automation/run` e `GET /automation/status` – utilitários para execuções em lote e inspeção de saídas.

### Frontend (React Router + Vite)
- Código em [frontend/app](frontend/app) criado via `create-react-router@latest` com TypeScript.
- UI construída com componentes do shadcn/ui (Button, Select, Dialog) adicionados via CLI.
- [frontend/app/routes/app.tsx](frontend/app/routes/app.tsx) implementa o painel:
  - Carrega docentes do backend com `GET /`.
  - Ao selecionar um docente, abre um diálogo para exportar DOCX (PDF placeholder).
  - Exibe link direto de download fornecido por `docx_url`.
- Tipos e cliente HTTP em [frontend/app/lib/api.ts](frontend/app/lib/api.ts).

---

## Fontes de Dados
- `data/base-de-dados-docente.csv`
- `data/docentes-experiencia-profissional.csv`
- `data/producao_docentes_detalhado.csv` (primeira linha é metadado e é ignorada pela importação)

---

## Preparação do Ambiente

### Backend
1. **Ativar o ambiente virtual**
   - PowerShell: `env\Scripts\Activate.ps1`
2. **Instalar/atualizar dependências** (se necessário):
   - `pip install -r requirements.txt`
3. **Popular o banco SQLite (apenas primeira execução ou quando os CSVs mudarem)**
   - `python -m backend.core.database`
4. **Executar o servidor Flask**
   - `python app.py`
   - O backend roda em `http://localhost:5000`.

### Frontend
1. **Instalar dependências**
   - `cd frontend`
   - `npm install`
2. **Verificar tipos (opcional)**
   - `npm run typecheck`
3. **Rodar o servidor de desenvolvimento**
   - `npm run dev`
   - A aplicação fica disponível em `http://localhost:5173`.

Garanta que o backend esteja ativo antes de abrir o painel, pois o frontend consome diretamente os endpoints em `http://localhost:5000`.

---

## Fluxo de Uso
1. Inicie o backend (`python app.py`).
2. Inicie o frontend (`npm run dev`) e abra `/app` no navegador.
3. Escolha um docente no seletor. O diálogo exibirá os formatos disponíveis.
4. Clique em **Exportar DOCX** para gerar o arquivo e use o link "baixar arquivo" que aponta para `/artifacts/<arquivo>`.
5. Os arquivos continuam disponíveis em `backend/exports/output/<accreditation>/`.

CLI alternativa (sem frontend):
- `python -m backend.services.automation --accreditation AACSB`
- `python -m backend.services.automation --accreditation AACSB --faculty 1 2 3`

---

## Notas Técnicas
- Logs do backend: console padrão (usa `logging` com nível `INFO`).
- `CSV_SPECS` em [backend/core/database.py](backend/core/database.py#L19-L35) controla a ordem/nomes dos CSVs.
- O endpoint `/artifacts/<path>` valida o caminho para evitar acesso fora da pasta configurada (`automation_service.output_root`).
- O frontend usa `VITE_API_BASE_URL` caso definido; senão, assume `http://localhost:5000`.

---

## Solução de Problemas
- **Docentes não aparecem no painel:** confirme se o backend responde em `http://localhost:5000/`. Use `curl` ou `Invoke-WebRequest` para inspecionar o retorno.
- **Exportação retorna erro:** o backend devolve mensagens JSON descrevendo o problema (`Docente não encontrado`, parâmetros ausentes, etc.).
- **Arquivo não baixa:** verifique se os DOCX estão sendo criados em `backend/exports/output` e se o caminho retornado em `docx_url` está acessível.
- **Mudanças nos CSVs:** ajuste o sanitizador de colunas em `backend/core/database.py` e reimporte os dados.

---

## Próximos Passos
- Implementar exportação em PDF para habilitar o botão já disponível no diálogo.
- Adicionar testes automatizados (unitários e E2E) para ingestão, geração de DOCX e chamadas do frontend.
- Publicar documentação de API (OpenAPI/Swagger) para facilitar integrações externas.
