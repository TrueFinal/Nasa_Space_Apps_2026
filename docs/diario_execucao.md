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

## 2026-11-14, 19:27 UTC / Europe/Lisbon — retomada após autenticação GitHub

Usuário informou configuração concluída. `gh auth status` confirmou sessão e `gh repo view` retornou `viewerPermission: WRITE`, `isEmpty: true`, sem branch padrão. `git ls-remote` confirmou ausência de referências. Como o remoto está vazio e a pasta contém o PDF e documentos locais, executados `git init`, configuração de `origin`, `git fetch` e criação de `feature/data-ingestion-mvp` nesta mesma pasta, sem mover ou sobrescrever arquivos.

Identidade configurada somente neste repositório a partir da conta autenticada retornada por `gh api user`: Lucas P. Nunes, com endereço privado GitHub `152216002+LucasPNunes1@users.noreply.github.com`. Criados `.gitignore` para dados/segredos/cache e `.env.example` sem credenciais. Nenhuma stack existente foi substituída.

Unidade de commit: `chore: initialize ingestion branch and technical plan`. Arquivos: PDF, cinco documentos de preflight, `.gitignore` e `.env.example`. Verificações: JSON de auditoria parseável, remoto vazio confirmado, revisão de arquivos e busca de segredos; não há código executável nesta unidade. Hash e confirmação do push serão registrados na próxima entrada após a operação.

### Publicação confirmada da unidade inicial

Commit `90dd7cecb91825d8315c3f758ab04f041c71878e` (`chore: initialize ingestion branch and technical plan`) enviado a `origin/feature/data-ingestion-mvp`; `git ls-remote` confirmou o mesmo hash. Branch com upstream configurado.

## 2026-11-14, 19:30 UTC / Europe/Lisbon — transporte, configuração e primeira coleta NOAA

Criados ambiente isolado Python 3.12 via uv (sem alterar o Python do sistema), dependências declaradas e lock das versões instaladas. Os módulos `core` e `noaa` separam transporte/proveniência da validação específica do índice. Configuração YAML contém produtos e regiões; caixa `brasilia_smoke` é provisória e exclusivamente técnica. Metadados de polígonos serão preservados; a primeira extração usa bounding box sem alegar máscara.

Transporte usa timeout, três tentativas limitadas, espera progressiva, arquivos `.part` descartados em falhas, validação antes da promoção atômica e nomes com hash para preservar revisões. Não há retomada por byte: temporários reiniciam, pois não foi validado suporte consistente a Range/ETag pelos provedores. Manifesto guarda SHA-256 e horários UTC/America/Sao_Paulo; reexecução confere conteúdo antes de reutilizar. Logs não recebem cabeçalhos ou queries assinadas.

Execução real: NOAA ASCII (14.752 bytes, SHA-256 com prefixo `1297887f581b6190`) e HTML original (98.060 bytes, prefixo `45a29af6d57b0a23`) baixados e validados. Série com 921 trimestres sobrepostos, de janeiro/1950 a setembro/2026, usando o mês central como rótulo. HTML oficial preservado integralmente; nenhuma fase foi inferida localmente. Dados estão em `data/raw/noaa_roni/RONI/global_index`, fora do Git. Segunda execução reutilizou ambos os arquivos sem novas transferências.

Validação: sete testes passaram (formato, registros inválidos/duplicados, ausência preservada, HTML indevido, corrupção e fusos); Ruff e `git diff --check` passaram. Unidade: `feat: collect and validate official NOAA RONI snapshots`. Arquivos: configuração, dependências/lock, módulos core/NOAA, testes e diário. Hash/push serão registrados após confirmação.

### Publicação confirmada da coleta NOAA

Commit `7e47644d1993d3eba116c74c2b24695137be38ff` (`feat: collect and validate official NOAA RONI snapshots`) enviado; `git ls-remote` confirmou o mesmo hash na branch de desenvolvimento.

## 2026-11-14, 19:36 UTC / Europe/Lisbon — descoberta e coletor NASA, CLI e inventário

Implementados `nasa.py`, CLI e script executável. As consultas CMR/Harmony confirmaram produtos/versões/variáveis e disponibilidade; a janela comum vem dos primeiros/últimos grânulos. A consulta regional registra a quantidade exata, pagina resultados e recusa coleções maiores que `--max-granules` (padrão 50, sem truncamento silencioso). MUR é opcional.

Harmony solicita um recorte por grânulo, preserva ID de job e retoma polling entre execuções. A submissão não tem retry automático após timeout, para evitar duplicar jobs de estado desconhecido. Retentativas HTTP de consultas e transferências são limitadas; respostas externas não são copiadas aos logs. O token só é passado ao endpoint Harmony, nunca à NOAA ou aos links assinados de staging, e não é persistido no manifesto.

Seleção temporal ocorre no CMR por interseção com o intervalo. Cada grânulo mantém seus registros nativos completos, inclusive se o período de uma observação mensal ultrapassar o intervalo pedido. Isso é explicitado no plano e manifesto; evita eliminar registros mensais pelo timestamp representativo ou cortar incorretamente dias MUR cujo intervalo catalogado atravessa meia-noite. O recorte do provedor é espacial e por variável, sem agregação. O inventário preserva tanto o intervalo do grânulo quanto os tempos lidos do arquivo.

Polígonos GeoJSON são validados em WGS84, preservados com hash e extraídos pelo envelope; não há máscara de polígono nesta entrega. Validação NetCDF lê todos os blocos das variáveis pedidas, conta ausências sem substituí-las, registra unidades/dimensões/atributos/resolução de coordenadas e rejeita recortes totalmente vazios ou fora da região.

Execução pública real de `--dry-run` (2015-12-01 a 2015-12-02): 2 grânulos IMERG diários, 1 mensal IMERG, 1 GLDAS, 1 MERRA-2 e 3 MUR por interseção temporal. Nenhum job ou download científico é submetido nesse modo. A CLI NOAA foi executada e reutilizou os arquivos íntegros.

Problema encontrado nos testes: uma tolerância espacial de uma célula poderia aceitar uma grade ampla demais. Corrigida para meio espaçamento; teste com arquivo sintético fora da região passou após correção. Arquivos sintéticos são gerados apenas em diretórios temporários de teste, nunca apresentados como dados reais.

Validação: 20 testes passaram, incluindo reexecução com job salvo sem nova submissão, limite de volume, paginação, modo dry-run sem transferência, corrupção, ausências e remoção de queries assinadas dos metadados. Ruff passou. Unidade: `feat: add CMR discovery and resumable NASA subset collection`; inclui NASA/CLI/script, novos testes e diário. Hash e resultado do push serão registrados após confirmação.

Execução real da CLI completa em janela curta: NOAA reutilizada e quatro datasets NASA registrados como falha por `EARTHDATA_TOKEN` ausente, com saída de processo 1. Inventário e manifesto gerados apesar das falhas parciais. Nenhum conteúdo NASA foi baixado e nenhum job foi submetido. README incluído nesta unidade com instalação, comandos, autenticação, limites e comportamento de recortes.

### Publicação confirmada do coletor NASA

Commit `84a52257dac3e5b8bd9c6206a74241e04caf8c96`, de 19:38 UTC, (`feat: add CMR discovery and resumable NASA subset collection`) enviado; referência remota confirmou o mesmo hash.

## 2026-11-14, 19:41 UTC / Europe/Lisbon — evidências, revisão de dependências e CI

Conferido o formato de submissão no código oficial de `nasa/harmony-py` (`harmony/client.py`) e adotado `collections/parameter_vars` com parâmetro `variable`, evitando nomes de grupos HDF5 embutidos no caminho. Teste verifica o contrato e a preservação da seleção temporal por grânulo.

Removidas dependências não utilizadas Xarray/Pandas e explicitados NumPy/tzdata. Lock regenerado e ambiente sincronizado; 20 testes e Ruff passaram novamente após essas alterações. Script `--help` validado. Documentos de arquitetura e decisões atualizados para refletir a implementação real.

`--inventory-only` confirmou dois arquivos NOAA, 112.812 bytes, ambos com SHA-256 válido; série com 921 registros, janeiro/1950 a setembro/2026 e zero sentinelas ausentes reconhecidas. Não há problemas de integridade identificados. A classificação está preservada no HTML original e não foi convertida em fases locais. Criado `docs/inventario_coleta.json` com cópia de manifesto/inventário e último resultado de execução para o time acompanhar sem versionar dados brutos. Campos científicos NASA permanecem não verificados.

Criado GitHub Actions para testes, Ruff e ajuda da CLI em Python 3.12 a cada push/PR. Actions checkout/setup-python foram consultadas em seus releases oficiais e fixadas por SHA de commit (v7.0.1 e v7.1.0). Workflow usa somente permissão de leitura do conteúdo, não requer credenciais Earthdata e não transfere dados científicos.

Unidade: `chore: add reproducible checks and collection evidence`. Arquivos: workflow, README, arquitetura/decisões/fontes/diário, snapshot de inventário, ajuste de parâmetros NASA/teste e dependências/lock. Verificações: 20 testes, Ruff, ajuda CLI, inventário com hashes, revisão de diff, JSON/YAML e busca de segredos. Hash, push e execução remota serão registrados após confirmação.
