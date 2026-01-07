# Lattes Exporter

## Visão Geral
- Gera pacotes de CV prontos para acreditação (DOCX + JSON) a partir dos dados dos docentes do Insper.
- Carrega os CSVs brutos em um banco SQLite local para consultas estruturadas.
- Oferece múltiplos modelos de acreditação com produção acadêmica resumida e janelas de experiência configuráveis.

## Componentes Principais
- [backend/core/database.py](backend/core/database.py): Povoa `data/lattes.sqlite3` a partir dos arquivos CSV, incluindo a produção acadêmica com tratamento da linha de preâmbulo do cabeçalho.
- [backend/services/automation.py](backend/services/automation.py): Monta perfis docentes, filtra experiências conforme regras de acreditação, resume produções e gera os arquivos DOCX/JSON.
- [backend/exports/output](backend/exports/output): Diretório de saída para as pastas de acreditação geradas (`aacsb`, `equis`, etc.).

## Fontes de Dados
- `data/base-de-dados-docente.csv`
- `data/docentes-experiencia-profissional.csv`
- `data/producao_docentes_detalhado.csv` (pula a primeira linha de metadados antes do cabeçalho)

## Preparação do Ambiente
- Ambiente virtual Python 3.11 localizado em `env/`.
- Dependências reunidas em [requirements.txt](requirements.txt) (Flask, python-docx, clientes SQLite, etc.).
- Variáveis de ambiente carregadas via `python-dotenv`; consulte [backend/core/config.py](backend/core/config.py) para utilitários de resolução de caminhos.

## Como Usar
1. **Ativar o ambiente**
   - Windows PowerShell: `env\Scripts\Activate.ps1`
2. **Carregar o banco**
   - `python -m backend.core.database`
   - Cria as tabelas quando necessário e evita recarregar dados já importados.
3. **Gerar CVs**
   - `python -m backend.services.automation --accreditation AACSB` (opcional `--faculty <id ...>` para filtrar docentes)
   - Produz arquivos DOCX e JSON por docente em `backend/exports/output/<accreditation>/`.

## Lógica de Acreditação
- Regras de acreditação definidas em `ACCREDITATION_RULES` (janela de experiência, limites, versão do modelo).
- Filtragem de experiência mantém vínculos dentro da janela configurada, considerando cargos em andamento mesmo sem data inicial explícita.
- Produção acadêmica resumida com no mínimo cinco registros, respeitando os limites de cada acreditação; títulos vazios são descartados.

## Solução de Problemas
- Caso o esquema dos CSVs mude, atualize `CSV_SPECS` em [backend/core/database.py](backend/core/database.py#L19-L35) para ajustar o mapeamento das colunas.
- Erros de banco ao carregar produções são registrados em log e a automação continua sem interromper a execução.
- Relatórios de execução (`run_<timestamp>.json`) documentam os docentes processados e os artefatos gerados.

## Próximos Passos
- Ampliar a automação para outras acreditações (EQUIS, AMBA e ABET já possuem estrutura inicial).
- Investigar testes automatizados para ingestão de dados e formatação dos documentos.
