# Fontes e verificação inicial de datasets

Consulta: 2026-11-14. Esta tabela descreve a auditoria pública de **metadados de coleção**. As respostas CMR/Harmony resumidas, parâmetros, datas e hashes consultados constam em `auditoria_fontes.json`. Após essa auditoria, foram executadas amostras autenticadas NASA; seu conteúdo efetivamente obtido está no inventário, não deve ser confundido com toda a cobertura temporal da coleção.

Atualização após implementação: NOAA e amostras NASA foram executadas e validadas. O inventário e a proveniência estão em [`inventario_coleta.md`](inventario_coleta.md) e [`inventario_coleta.json`](inventario_coleta.json). Os arquivos brutos permanecem locais e ignorados pelo Git. Falhas iniciais de EULA e integração foram resolvidas e permanecem registradas no diário.

| Fonte/produto | Versão | Coleção CMR | Último fim de grânulo encontrado (UTC) | Variáveis prioritárias confirmadas no catálogo |
|---|---|---|---|---|
| IMERG Final diário / GPM_3IMERGDF | 07 | C2723754864-GES_DISC | 2025-09-30T23:59:59.999Z | precipitation |
| IMERG Final mensal / GPM_3IMERGM | 07 | C2723754851-GES_DISC | 2025-09-30T23:59:59.999Z | Grid/precipitation |
| GLDAS Noah / GLDAS_NOAH025_M | 2.1 | C1342986036-GES_DISC | 2026-07-31T23:59:59.000Z | SoilMoi0_10cm_inst, SoilMoi10_40cm_inst, SoilMoi40_100cm_inst, SoilMoi100_200cm_inst, RootMoist_inst, Evap_tavg, Qs_acc, Qsb_acc |
| MERRA-2 / M2TMNXSLV | 5.12.4 | C1276812859-GES_DISC | 2026-09-30T23:59:59.000Z | U10M, V10M, SLP, T2M, TQV |
| MUR SST, opcional | 4.1 | C1996881146-POCLOUD | 2026-11-13T21:00:00.000Z | analysed_sst, analysis_error |

Todas essas coleções anunciaram serviço Harmony `sds/HOSS-geographic` com recorte espacial, temporal e por variável, inclusive suporte a geometria, e saída `application/netcdf`. As unidades das amostras retornadas estão no inventário: IMERG diário `mm/day`, mensal `mm/hr`; solo GLDAS `kg m-2`, evapotranspiração `kg m-2 s-1`; ventos MERRA-2 `m s-1`, pressão `Pa`, temperatura `K` e vapor `kg m-2`. Nenhuma média, conversão de unidade, regradeamento ou interpolação foi aplicada.

RONI: os GETs do [ASCII oficial](https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt) e da [tabela oficial de episódios](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/) retornaram 200. O ASCII possui `SEAS YR ANOM`, sem rótulo de fase; preservar também o HTML. Não reconstruir o RONI a partir de MUR.

## Referências oficiais consultadas

- [NASA CMR — documentação de busca](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html): consulta por produto/versão, identificadores, disponibilidade e grânulos.
- [NASA Harmony — API e capacidades](https://harmony.earthdata.nasa.gov/docs): `GET /capabilities?collectionId=<id>`, serviços e subsetting.
- [NASA GES DISC — migração para Earthdata Cloud](https://github.com/nasa/gesdisc-tutorials/blob/main/user-guidance/GES_DISC_Migration_to_Earthdata_Website_and_Earthdata_Cloud.md): descoberta CMR e substituição do acesso antigo.
- [NASA GPM — diretório de produtos](https://gpm.nasa.gov/data/directory) e [notas IMERG V07](https://gpm.nasa.gov/sites/default/files/2024-02/IMERG_V07_ReleaseNotes_240221.pdf): versões, mudanças de variáveis e distinção entre Final e NRT.
- [NASA GLDAS — acesso](https://ldas.gsfc.nasa.gov/gldas/gldas-get-data): produto e métodos oficiais de acesso.
- [NASA PO.DAAC — MUR v4.1](https://podaac.jpl.nasa.gov/dataset/MUR-JPL-L4-GLOB-v4.1): camada oceânica complementar.

## Pendências de acesso e cobertura

- Acesso GitHub, identidade, token Earthdata e aceite GES DISC configurados nesta execução; credenciais permanecem locais.
- Unidades, dimensões, resolução e ausências verificadas nas amostras retornadas. Qualidade científica regional e continuidade histórica não foram validadas.
- Verificar primeiro/último grânulo no período e região, continuidade e quantidade total antes de escolher janela de extração. A tabela registra apenas a consulta ordenada por último fim de grânulo.
- Selecionar região brasileira com polígono oficial e auditar estações ANA/INMET antes de recomendar um local. Nenhuma cobertura de estação foi confirmada neste preflight.
- ANA, INMET, SMAP, MODIS e NASA-SSH são extensões futuras e não têm coletores implementados.
