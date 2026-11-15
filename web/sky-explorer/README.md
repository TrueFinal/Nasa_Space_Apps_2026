# SPHEREx Sky Explorer

Aplicação web pública para animar imagens observadas do SPHEREx no tempo. A busca aceita graus decimais ou sexagesimais, campo de 60–1200 segundos de arco, DR1/QR3, seis detectores e os 102 canais espectrais. Cada frame combina exposições da mesma visita ou semestre escolhido; nunca anima o eixo espectral como se fosse tempo.

## Executar

```bash
npm ci
npm run build
npm run dev
```

Abra http://localhost:4173. O mesmo Worker fornece HTML/JS e um proxy com allowlist para os serviços científicos; o processamento dos FITS ocorre no navegador. Não precisa de credenciais de arquivo.

## Uso

- Use um dos cinco exemplos observados salvos ou informe coordenadas e clique em **Explorar dados atuais**.
- Troque detector/canal e consulte novamente para manter essa faixa em todos os frames.
- Reproduza, ajuste a velocidade ou escolha uma época. Compare com média ou diferença contra uma referência.
- Clique na imagem para um espectro exploratório de abertura; exporte CSV, proveniência, PNG ou GIF.
- O mapa Aladin sobrepõe o frame SPHEREx ao contexto WISE/DSS e ao catálogo Gaia com movimentos próprios lineares.
- Compartilhe com `?ra=133.7951291667&dec=-7.2451472222&fov=300&detector=6&band=detector&collection=both`.

Os exemplos usam uma seleção de 52 exposições reais: WISE0855 12, Barnard 10, Epsilon Indi B 15, RW Aur 6, R Dra 9. URLs, consultas e contagem do arquivo ficam nos JSONs. Barnard e Epsilon Indi B usam centros aproximados de 2026 por causa do movimento próprio; não confundir com as coordenadas J2000.

## Verificação

```bash
npm test
npx playwright install chromium # quando não houver navegador local
npx playwright test
```

Os testes científicos comparam a inversão TAN-SIP a valores Astropy independentes no FITS observado da IRSA; verificam máscaras, seleção espectral, coadd e separação entre tempo e bandas. Os testes de navegador abrem os cinco alvos, reproduzem, subtraem, medem e exportam, além de verificar layout móvel. `validation-targets.json` documenta os downloads reais.

Para refazer os exemplos a partir da raiz Python: `uv run --extra viz python web/sky-explorer/scripts/prepare_examples.py`. Os FITS ficam em `data/web_targets/`.

## Método e limites

WCS TAN-SIP, interpolação bilinear com máscara, pesos da variância e subtração do modelo zodiacal. SOURCE sozinho não é rejeitado; outros bits de FLAGS são conservadoramente mascarados. Este é o pipeline rápido no navegador, diferente da reprojeção por área exata disponível nos notebooks Python. As variâncias reprojetadas não incluem covariâncias de interpolação. O contraste é comum entre épocas. Combinar o detector inteiro mistura comprimentos de onda; isso é informado na interface.

O espectro usa abertura de 2 pixels e anel de fundo 4–6 pixels, em mJy. Os comprimentos de onda são os do centro do campo por exposição, não uma calibração CWAVE/CBAND para cada posição; as épocas são misturadas. Não substitui espectrofotometria científica da IRSA. Intervalos sem cobertura aparecem vazios, sem inventar dados. Não há classificação automática ou confirmação de movimento.

Consultas ao arquivo podem ter dados parciais ou limites: ambos são informados. Os exemplos salvos continuam disponíveis durante falhas temporárias externas. O proxy limita URLs a arquivos públicos SPHEREx da IRSA, valida coordenadas, usa tempo limite e cache HTTP. A atualização explícita ignora o cache da consulta, mas mantém cutouts cacheados por sete dias. Não há tarefas agendadas nem treino no servidor.

## Fontes

- [IRSA: acesso atual DR1 + QR3](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/)
- [IRSA: mosaicos e espectro exploratório](https://caltech-ipac.github.io/irsa-tutorials/spherex-mosaic/)
- [IRSA: cutouts e WCS](https://irsa.ipac.caltech.edu/ibe/cutouts.html)
- [CDS: Aladin e servidores alternativos](https://aladin.cds.unistra.fr/)
- [Gaia DR3, espelho GAVO](https://dc.g-vo.org/tableinfo/gaia.dr3lite)
- [SIMBAD: coordenadas e movimentos próprios](https://simbad.cds.unistra.fr/simbad/)

O pacote gifenc 1.0.3 é distribuído com sua licença em `worker/gifenc.LICENSE.txt`. Aladin Lite 3.9.2-beta é carregado do pacote oficial via jsDelivr.
