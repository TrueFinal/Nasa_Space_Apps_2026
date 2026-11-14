# Decisões técnicas

Estado atual: acesso GitHub resolvido; repositório vazio vinculado e branch publicada. Os registros abaixo preservam o motivo das decisões no momento em que foram tomadas.

## 2026-11-14 — respeitar o histórico oficial antes de implementar

O prompt exige desenvolvimento em `TrueFinal/Nasa_Space_Apps_2026` e inspeção do código existente. A pasta atual não é um clone e o remoto não está acessível sem autenticação. Manter apenas documentação de preflight e não criar um projeto/histórico Git paralelo. Consequência: implementação e branch aguardam acesso; nenhum push pode ser afirmado.

## 2026-11-14 — descoberta de dados em CMR e recorte em Harmony

A documentação oficial relata a migração GES DISC para Earthdata Cloud em 2026. Consultar CMR para coleções/grânulos e Harmony para capacidades; não construir URLs a partir de servidores antigos. As cinco coleções verificadas anunciam `sds/HOSS-geographic` com seleção espacial, temporal e de variáveis e saída NetCDF-4. A combinação deve ser validada no serviço selecionado, não apenas no resumo agregado de capacidades. Autenticação e execução real de jobs ainda não foram validadas.

Alternativa: arquivos globais por HTTPS. Evitar no MVP por volume desnecessário, sobretudo para MUR; não usar download global como fallback silencioso de um recorte que falhou.

## 2026-11-14 — variáveis publicadas prevalecem sobre nomes presumidos

O PDF menciona `precipitationCal`. A consulta atual ao Harmony lista `precipitation` em `GPM_3IMERGDF` V07 e `Grid/precipitation` em `GPM_3IMERGM` V07. Os nomes e caminhos efetivamente publicados devem ser preservados no manifesto. As notas de versão informam mudanças de nomes em V07; a inspeção do arquivo retornado ainda será necessária para confirmar conteúdo e unidades.

## 2026-11-14 — RONI oficial sem reconstrução/classificação própria

Preservar a série ASCII e a tabela HTML oficial de episódios, pois o ASCII traz `SEAS YR ANOM`, sem coluna de fase. Não gerar uma classificação apenas comparando o índice com ±0,5, nem substituir o índice por MUR. A classificação oficial envolve persistência e pode ser revisada. O HTML bruto deve permanecer disponível mesmo se uma tabela derivada vier a ser criada posteriormente.

## 2026-11-14 — disponibilidade observada, sem supor presente

A consulta do último grânulo encontrou datas diferentes entre fontes e IMERG até setembro/2025. Não atribuir automaticamente essa defasagem à latência aproximada de 3,5 meses. Reconsultar catálogo, verificar paginação, continuidade e região e registrar cobertura efetivamente obtida; metadados de coleção não comprovam integridade ou acesso ao conteúdo.

## 2026-11-14 — região brasileira configurável

Não há auditoria de estações ANA suficiente para justificar uma região definitiva. Manter seleção pendente entre bacia com estações, Cerrado agrícola e área ribeirinha. Critérios futuros: continuidade por variável, lacunas, qualidade, compatibilidade de escala e polígono oficial. GLDAS representa modelo de superfície terrestre; não usar extração oceânica vazia para alegar sucesso de coleta.

## 2026-11-14 — implementar ingestão sem camada de análise

Python 3.12 isolado por uv e leitura direta com netCDF4/NumPy permitem preservar valores empacotados, grupos e atributos sem conversões implícitas. Xarray/Pandas não são dependências desta etapa. Requests acessa APIs REST oficiais para manter timeout/retries e sanitização explícitos; Harmony-Py é uma alternativa oficial recomendada pelo provedor, mas não foi necessário adicionar outro cliente nesta implementação. O formato de submissão com `collections/parameter_vars` e parâmetro `variable` também foi conferido no código oficial de `nasa/harmony-py`.

## 2026-11-14 — seleção por grânulo e envelope explícitos

Selecionar temporalmente por interseção CMR e preservar os registros nativos completos de cada grânulo. Um mensal mantém a cobertura mensal mesmo em consulta curta; o manifesto distingue pedido, consulta, cobertura de grânulo e tempos lidos. Não aplicar subset temporal adicional sobre um timestamp representativo do mês ou dia MUR. Recortes de polígonos usam somente o envelope, claramente rotulado; máscara e médias por área são trabalhos posteriores.

## 2026-11-14 — execução limitada e verificável

Recusar datasets acima do limite de grânulos configurado em vez de truncar. Um resultado por grânulo é esperado; múltiplos links, resultados vazios ou fora da região são reportados como erro para revisão. Jobs são persistidos e retomados; arquivos temporários reiniciam porque suporte consistente a retomada por byte não foi comprovado. Scripts usam um processo por diretório de saída, sem prometer concorrência no manifesto.
