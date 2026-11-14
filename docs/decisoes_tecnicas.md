# Decisões técnicas

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
