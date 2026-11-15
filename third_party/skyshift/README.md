# Referência SkyShift

Repositório: https://github.com/cucuradu/skyshift

Licença Apache-2.0, preservada integralmente em [LICENSE](LICENSE).

`src/spherex_tracking/infrared_display.py` e `web/infrared-mask/plate.mjs` implementam,
em Python e JavaScript, uma adaptação da política de plotagem de:

- `web/src/learn/data.ts`: `cropAround`, `gaiaInCrop` e escopo de previsões de objetos móveis;
- `web/src/learn/plate.ts`: remoção do céu somente para display e desenho limitado ao recorte;
- `web/src/blink/math.ts`: percentis robustos, contraste e transformação asinh comum entre épocas.

Adaptações Zephyr: WCS FITS nativo com origem inferior, cobertura efetiva e flags de cada
pixel, rejeição de posições sem imagem/fora da faixa selecionada, interrupção de linhas
em lacunas e sessões distintas, orientação N/E do WCS, e exportação científica PNG.
Não são usadas imagens de alvos SkyShift em coordenadas diferentes das do alvo MPC/MOST.
As imagens deste piloto são os recortes SPHEREx reais do Slipher já identificados no manifesto.
