# Diário de execução — Earth Detectives

## 2026-11-14, 18:10 UTC / Europe/Lisbon — preflight da etapa 0

**Estado:** planejamento e verificação de acesso; etapa 1 ainda não implementada.

### O que foi feito e por quê

- Leitura integral de `earth_detectives_enso.pdf` (capa, sumário e 21 páginas numeradas), extraído com `pdftotext -layout`, e do prompt fornecido. O escopo autorizado é a ingestão e auditoria técnica, sem EDA, limpeza definitiva, estatística ou interface.
- Inspeção da pasta atual e busca de `AGENTS.md`: somente `docs/earth_detectives_enso.pdf` existia; nenhum repositório Git ou instrução local de agentes foi encontrado. Não havia código, dependências ou convenções locais para examinar.
- Verificação do ambiente: Git 2.25.1, Python 3.8.10, pip, requests, curl e uv disponíveis. `python` não existe; o interpretador disponível é `python3`.
- Tentativa de ler as referências remotas oficiais por HTTPS (`git ls-remote https://github.com/TrueFinal/Nasa_Space_Apps_2026.git`): falhou por falta de autenticação. A página pública retornou 404, o que não distingue repositório privado de URL inexistente.
- Verificação SSH com autenticação não interativa: `Permission denied (publickey)`. Nenhuma chave estava disponível. A chave pública do host GitHub foi adicionada ao `known_hosts` pelo cliente SSH.
- GitHub CLI inicialmente ausente. Instalado `gh` v2.104.0 em `/home/tatiana/.local/bin/gh`, a partir do release oficial `cli/cli`, verificando o SHA-256 do arquivo contra o manifesto do release. `gh auth status` confirma ausência de sessão. Não foram modificadas configurações de identidade Git; nome/e-mail não estavam definidos.
- Solicitada configuração local segura de autenticação e identidade, sem envio de segredos na conversa.

### Fontes e método de consulta

- NOAA CPC: HTTP GET da série oficial RONI e da página de episódios; ambos retornaram 200. Série com cabeçalho `SEAS YR ANOM`; a página HTML é necessária para preservar a classificação oficial, que não está como coluna na série ASCII. As respostas foram verificadas em memória; nenhum dado observacional foi salvo no projeto.
- NASA CMR: `GET /search/collections.umm_json?short_name=<produto>&page_size=20`; seleção explícita da versão pretendida. Depois, `GET /search/granules.json?collection_concept_id=<id>&sort_key=-end_date&page_size=1` para identificar o último grânulo catalogado.
- NASA Harmony: `GET /capabilities?collectionId=<id>` para verificar variáveis e capacidades de recorte por coleção e por serviço. Apenas consultas públicas de metadados; nenhum job de extração foi submetido.
- Documentação oficial de migração GES DISC, notas de versão IMERG e APIs CMR/Harmony consultadas. Links em `fontes_e_datasets.md`.

### Problemas e decisões

- Acesso ao repositório oficial indisponível: não foi possível clonar, examinar branches/commits ou criar uma branch baseada no histórico da equipe. Não foi inicializado um histórico independente na pasta.
- Não há credenciais Earthdata nas variáveis verificadas (`EARTHDATA_USERNAME`, `EARTHDATA_PASSWORD`, `EARTHDATA_TOKEN`) nem arquivo `~/.netrc`. Downloads NASA autenticados ainda não foram testados.
- GES DISC migrou acesso para Earthdata Cloud em 2026; evitar URLs construídas para servidores antigos. Descobrir arquivos pelo CMR e serviços pelo Harmony.
- Variáveis IMERG no catálogo diferem do nome `precipitationCal` do PDF: diário `precipitation`, mensal `Grid/precipitation`. Usar nomes efetivamente publicados e preservá-los no manifesto.
- Últimos grânulos catalogados encontrados: IMERG diário/mensal até 2025-09-30, GLDAS até 2026-07-31, MERRA-2 até 2026-09-30 e MUR até 2026-11-13. Isso não comprova continuidade das séries nem disponibilidade de download. Não atribuir a diferença apenas à latência nominal.
- Nenhuma região brasileira foi escolhida. GLDAS não deve usar uma região oceânica como teste representativo da resposta terrestre.

### Resultado e verificações

- Planejamento preservado em `arquitetura_dados.md` e `decisoes_tecnicas.md`; auditoria de metadados em `auditoria_fontes.json`.
- Nenhum dataset observacional obtido em disco, nenhum script de ingestão implementado, nenhum teste de software aplicável nesta entrada. Consultas de metadados são verificação de disponibilidade, não testes do futuro coletor.
- O PDF original foi preservado. Não foram gravadas credenciais ou dados científicos volumosos.

### Versionamento

- Repositório pretendido: https://github.com/TrueFinal/Nasa_Space_Apps_2026
- Branch pretendida: `feature/data-ingestion-mvp`, sujeita à verificação de existência no remoto.
- Branch efetiva: nenhuma; clone bloqueado por autenticação.
- Commit/hash/mensagem: não aplicável; nenhum commit criado.
- Arquivos locais criados nesta unidade: `docs/diario_execucao.md`, `docs/decisoes_tecnicas.md`, `docs/fontes_e_datasets.md`, `docs/arquitetura_dados.md`, `docs/auditoria_fontes.json`.
- Push: não realizado; falta autenticação e acesso ao histórico oficial.
- Após cada futuro push confirmado, registrar o hash na entrada subsequente. O último hash pode ser consultado com `git log`; não tentar inserir o hash de um commit dentro dele mesmo. Nunca registrar push como realizado antes da confirmação do remoto.

## 2026-11-14, 18:13 UTC / Europe/Lisbon — documentação e evidências preservadas

Criados os cinco documentos listados acima para manter o planejamento e a auditoria recuperáveis enquanto o acesso oficial está indisponível. `auditoria_fontes.json` contém parâmetros, horários UTC e America/Sao_Paulo, hashes das representações locais consultadas, capacidades Harmony e último grânulo CMR de cada produto. Os horários são os de gravação das respostas de preflight, não os tempos das observações.

Validação executada: leitura do JSON, confirmação de cinco produtos, correspondência dos identificadores de coleção e presença do serviço `sds/HOSS-geographic` em todos eles. Busca local por padrões comuns de tokens/senhas não encontrou correspondências nos documentos. Conferido novamente `gh --version` e `gh auth status`: CLI funcional e sessão ausente.

Resultado: preflight e documentação local concluídos; implementação da etapa 1 e exame do histórico oficial continuam pendentes do acesso GitHub. Nenhuma branch, commit ou push foi criado. Nenhum job autenticado NASA foi submetido e nenhum arquivo científico foi salvo no projeto. Esta entrada não representa entrega da etapa 1.

## 2026-11-14 — retomada após autenticação GitHub

Usuário informou configuração concluída. `gh auth status` confirmou sessão e `gh repo view` retornou `viewerPermission: WRITE`, `isEmpty: true`, sem branch padrão. `git ls-remote` confirmou ausência de referências. Como o remoto está vazio e a pasta contém o PDF e documentos locais, executados `git init`, configuração de `origin`, `git fetch` e criação de `feature/data-ingestion-mvp` nesta mesma pasta, sem mover ou sobrescrever arquivos.

Identidade configurada somente neste repositório a partir da conta autenticada retornada por `gh api user`: Lucas P. Nunes, com endereço privado GitHub `152216002+LucasPNunes1@users.noreply.github.com`. Criados `.gitignore` para dados/segredos/cache e `.env.example` sem credenciais. Nenhuma stack existente foi substituída.

Unidade de commit: `chore: initialize ingestion branch and technical plan`. Arquivos: PDF, cinco documentos de preflight, `.gitignore` e `.env.example`. Verificações: JSON de auditoria parseável, remoto vazio confirmado, revisão de arquivos e busca de segredos; não há código executável nesta unidade. Hash e confirmação do push serão registrados na próxima entrada após a operação.
