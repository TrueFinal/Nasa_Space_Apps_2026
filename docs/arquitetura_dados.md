# Arquitetura proposta para a ingestão — etapa 1

Estado em 2026-11-14: **proposta, ainda sem implementação**. A pasta contém a especificação e documentos de preflight; o clone oficial depende de autenticação. A organização abaixo deve ser ajustada às convenções do repositório assim que ele estiver acessível.

## Fluxo e responsabilidades

1. `config/datasets.yaml`: produtos, versões, variáveis solicitadas e seleção de fontes. Metadados consultados no provedor prevalecem sobre suposições estáticas.
2. `config/regions.yaml`: regiões identificadas e geometrias GeoJSON em EPSG:4326. Niño 3.4: oeste -170, sul -5, leste -120, norte 5. Região brasileira permanece configurável e sem escolha definitiva.
3. `scripts/fetch_mvp_data.py`: CLI com seleção de datasets, região, início/fim, diretório de saída e `--dry-run`. Validar parâmetros antes de transferir dados.
4. Clientes NOAA e NASA: NOAA preserva ASCII e HTML oficial; NASA consulta CMR, verifica capacidades por serviço no Harmony, seleciona variáveis existentes e solicita recortes sem agregação, interpolação ou regradeamento.
5. Transferência: timeout, tentativas limitadas com espera progressiva, registro de falhas, arquivo temporário, verificação de conteúdo e publicação atômica do arquivo completo. Retomar transferência somente quando o serviço e seus validadores HTTP permitirem; caso contrário reiniciar o temporário. Guardar o ID de jobs assíncronos para não submetê-los novamente desnecessariamente.
6. `data/raw/<fonte>/<produto>/<região>/`: arquivos originais recebidos ou recortes produzidos pelo provedor; o manifesto distingue esses dois métodos. Não alterar arquivos após validação. Conferir SHA-256 para reutilização e oferecer atualização explícita das fontes revisáveis, como RONI.
7. `data/metadata/manifest.json` e `dataset_catalog.csv`: proveniência por arquivo e inventário resumido. `logs/ingestion.log`: tentativas e erros sem credenciais, cabeçalhos de autorização ou URLs assinadas.
8. Auditoria técnica: leitura de cabeçalhos e integridade NetCDF/HDF5 com xarray e backend compatível; conferir variáveis, unidades, dimensões, coordenadas, tempos, flags e valores ausentes quando viável sem limpeza. Metadados desconhecidos devem ficar nulos com justificativa, nunca inferidos silenciosamente.

Não criar diretórios vazios. Dados, cache, logs, `.env`, `.netrc` e arquivos temporários ficam fora do Git. Código, configuração, testes, documentação e pequenos metadados de auditoria podem ser versionados.

## Ordem de implementação após acesso ao repositório

1. Sincronizar referências, examinar histórico/alterações e criar branch própria sem sobrescrever trabalho existente.
2. Estrutura mínima, configuração, proteção de arquivos e CLI em dry-run.
3. Coletor NOAA RONI com preservação da classificação oficial; testar integridade e repetição.
4. Descoberta NASA CMR/Harmony, autenticação por ambiente ou mecanismo oficial local, recortes e registro de jobs.
5. IMERG Final diário/mensal, GLDAS Noah 2.1 e MERRA-2 mensal, começando por amostras pequenas explicitamente identificadas. MUR somente quando solicitado/habilitado, com recorte restrito.
6. Manifesto, inventário, testes de falhas/corrupção/reexecução, execução real e documentação de reprodução.

As dependências Python e versões serão escolhidas após examinar a stack oficial. Há Python 3.8.10 local e uv disponível; avaliar um ambiente isolado com Python suportado pelas bibliotecas científicas atuais, sem substituir o Python do sistema.

## Janela, região e limites

A janela histórica comum deve ser calculada a partir da disponibilidade das coleções selecionadas, seguida da verificação dos grânulos no período e região; não basta assumir datas do PDF. Com MUR, o início não pode anteceder 2002-05-31. O fim deve respeitar o último grânulo efetivamente disponível em cada fonte. Uma coleta parcial deve informar lacunas e limites/paginação; nunca aparentar que extraiu o histórico inteiro.

O `--dry-run` consulta metadados públicos e apresenta produtos, variáveis, período limitado, geometria, serviços, autenticação necessária e estimativas disponíveis. Não submete jobs nem baixa dados científicos.

Polígonos devem ser validados, preservados e identificados pelo conteúdo. Se um serviço oferecer apenas bounding box, registrar a extração como bounding box do polígono, sem afirmar que foi aplicada máscara. Para GLDAS, exigir região terrestre adequada; Niño 3.4 serve à investigação oceânica/atmosférica.

## Proveniência mínima

Por arquivo: fonte/organização, produto/versão, coleção/DOI, variáveis/unidades, resoluções, período pedido e retornado, região/CRS/geometria, URL pública estável, serviço/parâmetros, método, tamanho/SHA-256, qualidade, status e tentativas. Distinguir tempos das observações de `retrieved_at_utc` e `retrieved_at_local` em `America/Sao_Paulo`.

O diário usa data e fuso explícitos; os horários de comunicação com a equipe usam Europe/Lisbon. Não registrar segredos. Guardar metadados suficientes para reproduzir a seleção, sem expor tokens, cookies ou parâmetros de URLs assinadas.

## Entrega e encerramento

Commits lógicos e pushes verificados a cada unidade: planejamento, estrutura, NOAA, NASA/coletores, integridade/inventário e documentação final. Registrar arquivos, testes, resultado, hash e status real de publicação no diário. Sem force push.

Ao terminar a coleta, apresentar o inventário e os bloqueios e parar. EDA, limpeza, climatologias, estatística e interface dependem de discussão posterior.
