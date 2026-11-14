# Fontes e verificação inicial de datasets

Consulta: 2026-11-14. Esta é uma auditoria pública de **metadados**, não um inventário de arquivos científicos baixados. Nenhum download autenticado NASA foi executado. As respostas CMR/Harmony resumidas, parâmetros, datas e hashes das respostas consultadas constam em `auditoria_fontes.json`.

Atualização após implementação: a coleta NOAA foi executada e validada. O inventário e a proveniência dos dois arquivos obtidos, junto às falhas de acesso NASA, estão em [`inventario_coleta.json`](inventario_coleta.json). Os arquivos brutos permanecem locais e ignorados pelo Git.

| Fonte/produto | Versão | Coleção CMR | Último fim de grânulo encontrado (UTC) | Variáveis prioritárias confirmadas no catálogo |
|---|---|---|---|---|
| IMERG Final diário / GPM_3IMERGDF | 07 | C2723754864-GES_DISC | 2025-09-30T23:59:59.999Z | precipitation |
| IMERG Final mensal / GPM_3IMERGM | 07 | C2723754851-GES_DISC | 2025-09-30T23:59:59.999Z | Grid/precipitation |
| GLDAS Noah / GLDAS_NOAH025_M | 2.1 | C1342986036-GES_DISC | 2026-07-31T23:59:59.000Z | SoilMoi0_10cm_inst, SoilMoi10_40cm_inst, SoilMoi40_100cm_inst, SoilMoi100_200cm_inst, RootMoist_inst, Evap_tavg, Qs_acc, Qsb_acc |
| MERRA-2 / M2TMNXSLV | 5.12.4 | C1276812859-GES_DISC | 2026-09-30T23:59:59.000Z | U10M, V10M, SLP, T2M, TQV |
| MUR SST, opcional | 4.1 | C1996881146-POCLOUD | 2026-11-13T21:00:00.000Z | analysed_sst, analysis_error |

Todas essas coleções anunciaram serviço Harmony `sds/HOSS-geographic` com recorte espacial, temporal e por variável, inclusive suporte a geometria, e saída `application/netcdf`. Isso indica capacidade anunciada, sem comprovar funcionamento autenticado ou unidades dos arquivos. Não aplicar média, regradeamento ou interpolação nesta etapa.

RONI: os GETs do [ASCII oficial](https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt) e da [tabela oficial de episódios](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/) retornaram 200. O ASCII possui `SEAS YR ANOM`, sem rótulo de fase; preservar também o HTML. Não reconstruir o RONI a partir de MUR.

## Referências oficiais consultadas

- [NASA CMR — documentação de busca](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html): consulta por produto/versão, identificadores, disponibilidade e grânulos.
- [NASA Harmony — API e capacidades](https://harmony.earthdata.nasa.gov/docs): `GET /capabilities?collectionId=<id>`, serviços e subsetting.
- [NASA GES DISC — migração para Earthdata Cloud](https://github.com/nasa/gesdisc-tutorials/blob/main/user-guidance/GES_DISC_Migration_to_Earthdata_Website_and_Earthdata_Cloud.md): descoberta CMR e substituição do acesso antigo.
- [NASA GPM — diretório de produtos](https://gpm.nasa.gov/data/directory) e [notas IMERG V07](https://gpm.nasa.gov/sites/default/files/2024-02/IMERG_V07_ReleaseNotes_240221.pdf): versões, mudanças de variáveis e distinção entre Final e NRT.
- [NASA GLDAS — acesso](https://ldas.gsfc.nasa.gov/gldas/gldas-get-data): produto e métodos oficiais de acesso.
- [NASA PO.DAAC — MUR v4.1](https://podaac.jpl.nasa.gov/dataset/MUR-JPL-L4-GLOB-v4.1): camada oceânica complementar.

## Pendências de acesso e cobertura

- Configurar acesso GitHub ao repositório oficial e identidade para os commits.
- Configurar credenciais Earthdata localmente e autorizações exigidas pelos serviços; não enviar credenciais na conversa ou versioná-las.
- Confirmar unidades, dimensões, resolução e qualidade nos arquivos efetivamente retornados; metadados não disponíveis permanecem desconhecidos.
- Verificar primeiro/último grânulo no período e região, continuidade e quantidade total antes de escolher janela de extração. A tabela registra apenas a consulta ordenada por último fim de grânulo.
- Selecionar região brasileira com polígono oficial e auditar estações ANA/INMET antes de recomendar um local. Nenhuma cobertura de estação foi confirmada neste preflight.
- ANA, INMET, SMAP, MODIS e NASA-SSH são extensões futuras e não têm coletores implementados.
