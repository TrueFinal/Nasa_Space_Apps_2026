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

### Publicação e CI confirmados

Commit `b9ba10bab87c1d3eca69edf206f1c5b0cea21ca5` (`chore: add reproducible checks and collection evidence`) enviado; `git ls-remote` confirmou o hash. GitHub Actions [43633505673](https://github.com/TrueFinal/Nasa_Space_Apps_2026/actions/runs/43633505673) concluiu com `success`, confirmado por `gh run watch --exit-status`. O mesmo conjunto de 20 testes, Ruff e ajuda da CLI foi aprovado no runner remoto.

## 2026-11-14, 19:43 UTC / Europe/Lisbon — apresentação do inventário e encerramento da execução disponível

Criado `docs/inventario_coleta.md` para leitura rápida dos arquivos reais, bytes, período, integridade e limitações, com referência às evidências JSON. README atualizado com o link. Repositório e branch oficiais sincronizados; dados brutos, logs, ambiente e credenciais fora do Git. A configuração Earthdata continua pendente; não declarar concluída a aquisição NASA nem a etapa 1 integralmente. Nenhuma EDA foi iniciada.

Unidade: `docs: report collection inventory and verified publication`. Arquivos: inventário Markdown, README e diário. Verificação aplicável: correspondência da tabela com o inventário JSON, links locais e `git diff --check`; sem mudança de código. O hash desta última unidade pode ser recuperado com `git log -1 --format=%H` e será informado na entrega. Conforme o procedimento do diário, um commit não inclui seu próprio hash; seu hash é registrado na próxima entrada ou no relato da entrega após confirmar o remoto.

### Confirmação da publicação anterior

Commit `1cafd9fcd4a8aebc023957adce73c3821e223830` enviado e confirmado; CI [43633629342](https://github.com/TrueFinal/Nasa_Space_Apps_2026/actions/runs/43633629342) passou. Nenhuma alteração local pendente ao retomar a coleta.

## 2026-11-14, 19:48 UTC / Europe/Lisbon — execução autenticada e correção do contrato Harmony

Usuário confirmou configuração Earthdata. Presença do token verificada sem exibir seu conteúdo; `.env` continua ignorado pelo Git. Executada amostra mensal dezembro/2015 de IMERG, GLDAS e MERRA-2. Token aceito e jobs criados.

Encontrado desvio entre documentação textual e comportamento real: passar múltiplas variáveis separadas por vírgula em um único parâmetro `variable` retorna HTTP 400 (coverages não encontradas). Corrigido para parâmetros `variable` repetidos. Teste de regressão incluído; 21 testes e Ruff passaram. Após a correção, GLDAS e MERRA-2 aceitaram as requisições.

Jobs autenticados falharam no serviço HOSS: IMERG `a0c6fd3d-8ae9-433f-8cd4-dc2165d641f5`, GLDAS `75775008-b158-4c52-9c32-dd5c619ae4a9`, MERRA-2 `e5be210b-236c-4c40-baf1-f1ffa67dea97`. O diagnóstico do job IMERG e GET direto do `.dmr.xml` indicam HTTP 403 interno ao ler o arquivo `.dmrpp` na origem. Isso não é evidência de token ausente/inválido.

Investigada alternativa oficial: URLs HTTPS publicadas pelo CMR responderam HEAD 200 com ETag e Accept-Ranges bytes. Tamanhos globais anunciados: IMERG mensal 18.667.200 bytes; GLDAS 24.888.811; MERRA-2 78.811.779. Não foram baixados esses arquivos completos. Próxima unidade avaliará leitura de blocos HDF5 por HTTP Range, com recorte espacial local e preservação dos valores/metadados; o manifesto deverá distinguir esse método de um recorte feito pelo Harmony.

Unidade: `fix: serialize Harmony variables as repeated parameters`. Arquivos: coletor NASA, teste e diário. Verificações: 21 testes, Ruff, revisão de diff e execução autenticada descrita acima. Push/hash registrados após confirmação.

### Publicação da correção de parâmetros

Commit `d7bdb0035aa2482872610a246775809ad7b4220b` (`fix: serialize Harmony variables as repeated parameters`) enviado; referência remota confirmou o mesmo hash.

## 2026-11-14, 19:55 UTC / Europe/Lisbon — causa do 403 e preflight de autorização

GET autenticado da origem retornou JSON com `error_description: EULA Acceptance Failure` e URL oficial `https://urs.earthdata.nasa.gov/approve_app?client_id=e2WVk8Pw6weeLUKZYOxvTQ`. O HEAD 200 não garantia acesso; a causa do 403 envolve as condições pendentes da aplicação GES DISC, e não apenas indisponibilidade de metadados no HOSS. Solicitado ao titular ler e aceitar as condições na página oficial, sem transmitir credenciais.

A alternativa de leitura HDF5 por Range foi avaliada e descartada antes de versionar: o GET também é bloqueado pela mesma EULA. Código exploratório removido e dependências de exploração desinstaladas; nenhuma grade global foi baixada. Não há tentativa de contornar a autorização do provedor.

Implementada verificação mínima de conteúdo antes da submissão: GET streaming com Range bytes=0-7, somente nas origens NASA permitidas, valida assinatura do formato e fecha a resposta sem consumir o arquivo global. HTTP 403 com EULA produz mensagem própria com link de aceite. O identificador público da aplicação pode ser mantido; queries adicionais e tokens não são expostos. Isso evita novos jobs destinados a falhar por esse motivo.

Execução real confirmou essa mensagem para IMERG diário e mensal, GLDAS e MERRA-2. Não foram criados novos jobs nesses preflights. Amostras: diário em 2015-12-01 a 2015-12-02 e mensais em dezembro/2015. Nenhum conteúdo científico dessas quatro coleções foi obtido. Teste independente de MUR em andamento; resultado será registrado ao terminar.

Validação: 24 testes passaram, incluindo link EULA sanitizado, leitura mínima e recusa de envio de token a origem não permitida; Ruff passou. Unidade prevista: `fix: preflight NASA data access and explain pending EULA`. Arquivos: core/NASA, testes, README, decisões, diário e evidências de inventário. Push/hash registrados após confirmação.

## 2026-11-14, 19:57 UTC / Europe/Lisbon — aceite confirmado e autenticação dos resultados Harmony

Usuário informou aceite concluído. Iniciada nova execução mensal com `--refresh`, porque os três jobs anteriores estavam definitivamente falhos. A confirmação anterior por token não foi tratada como aceite de condições; o titular realizou a ação na página oficial.

Teste MUR independente criou job `874ec672-8db8-4b12-8c43-bddfaea10708`, concluído com sucesso pelo provedor. Encontradas duas incompatibilidades de execução: seleção de URL por sufixo `data#` também correspondia a `metadata#` (corrigida para igualdade exata da relação ESIP); e o link Harmony `service-results` exigia autenticação antes do redirecionamento ao arquivo. Sem header retornava HTML de login HTTP 200, corretamente rejeitado pelo validador NetCDF. Com header no host Harmony retornou NetCDF de 5.234.208 bytes. Nenhum HTML foi promovido a dado científico.

Transporte agora permite headers explícitos no download. O coletor envia o token somente quando o resultado permanece no host Harmony; links externos recebem nenhum header de autorização e redirecionamentos entre hosts seguem a remoção de Authorization feita pelo requests. URLs assinadas continuam sem query no manifesto/log. Teste parametrizado cobre link Harmony versus link externo. MUR será retomado pelo job existente após a amostra mensal, sem duplicar o job.

Validação: 26 testes e Ruff passaram. Unidade consolidada: `fix: validate NASA access and authenticate Harmony results`. Arquivos: core/NASA, testes, README, decisões e diário. Inclui preflight EULA, relação ESIP exata e autenticação no resultado Harmony. Resultado das coletas reais e hashes serão registrados na próxima unidade de inventário.

### Publicação e CI da integração autenticada

Commit `d1bb63927783ac4e5e8b53514366f4208ddeb04e` (`fix: validate NASA access and authenticate Harmony results`) enviado e confirmado no remoto. CI [43634888272](https://github.com/TrueFinal/Nasa_Space_Apps_2026/actions/runs/43634888272) concluiu com sucesso, incluindo os 26 testes.

## 2026-11-14, 20:02 UTC / Europe/Lisbon — amostras NASA obtidas e auditoria final

Após aceite pelo usuário, executados novos jobs mensais para dezembro/2015. Os três produtos foram obtidos e validados:

- IMERG mensal: 1 arquivo, 44.180 bytes, grade 11 × 11, `Grid/precipitation` em `mm/hr`.
- GLDAS: 1 arquivo, 83.186 bytes, grade 4 × 4, oito variáveis; solo e escoamento em `kg m-2`, evapotranspiração em `kg m-2 s-1`.
- MERRA-2: 1 arquivo, 86.639 bytes, grade 21 lat × 81 lon; U10M/V10M em `m s-1`, SLP em `Pa`, T2M em `K`, TQV em `kg m-2`.
- IMERG diário: 2 arquivos, 71.375 bytes, 01–02/12/2015, grades 11 × 11, `precipitation` em `mm/day`.
- MUR: 2 arquivos, 10.448.477 bytes, registros 01–02/12/2015 às 09h, grades 1001 lat × 5001 lon; `analysed_sst` e `analysis_error` em `kelvin`.

MUR foi solicitado para 01/12 e inclui 02/12 por interseção com a cobertura nativa do grânulo; nenhuma truncagem temporal ou agregação foi aplicada. Os arquivos mensais têm um timestamp representativo; cobertura mensal e tempo da coordenada permanecem distintos no manifesto. A precipitação mensal não foi convertida em acumulado, e nenhuma unidade foi alterada.

Somando NOAA (2 arquivos, 112.812 bytes), a coleta possui **9 arquivos e 10.846.669 bytes**, dos quais sete são recortes científicos NASA. Nenhuma grade global foi baixada. Não foram identificados problemas de integridade; zero valores ausentes reconhecidos nas variáveis selecionadas destas amostras. Isso não comprova continuidade histórica ou qualidade regional e não autoriza conclusões climáticas.

Repetidas as três execuções NASA com os mesmos parâmetros. A verificação bloqueava novas chamadas de download ou submissão e manteve consultas de metadados reais: os sete arquivos NASA foram reutilizados, conjunto de sete jobs e nove hashes inalterados. `--inventory-only` confirmou todos os hashes e ausência de arquivos `.part`.

Atualizados inventários Markdown/JSON, fontes, arquitetura e README para refletir a coleta real. Snapshot JSON guarda arquivos, proveniência, último resultado por dataset e verificação de repetição. Dados brutos e credenciais permanecem ignorados. A extração histórica completa não foi realizada: a caixa brasileira continua provisória e a escolha científica de região ainda deve ser discutida. Nenhuma EDA foi iniciada.

Unidade: `docs: publish verified NASA sample inventory`. Arquivos: README, arquitetura, fontes, inventários e diário. Verificações: todos os arquivos/hashes, períodos/variáveis/unidades lidos dos NetCDF, reexecução sem transferências, JSON válido, ausência do token nos arquivos versionáveis e `git diff --check`. Código já validado por 26 testes e CI no commit anterior; esta unidade altera somente documentos. O hash desta última unidade será informado na entrega após confirmar o push.
