import argparse
import json

from .fits_io import inventory_path


def main():
    parser = argparse.ArgumentParser(description="Protótipo científico de Shift-and-Stack")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Executar injeção sintética e campos de controle")
    demo.add_argument("--output", default="outputs/demo")
    demo.add_argument("--seed", type=int, default=42)
    demo.add_argument("--null-trials", type=int, default=8)
    inspect = sub.add_parser("inspect", help="Inspecionar metadados FITS sem empilhar")
    inspect.add_argument("path", help="Arquivo FITS ou diretório de dados")
    real = sub.add_parser("real", help="Baixar e analisar uma sequência real do SPHEREx DR1")
    real.add_argument("--data-dir", default="data/spherex")
    real.add_argument("--output", default="outputs/spherex")
    papers = sub.add_parser("papers", help="Comparar métodos de Gural e Stetzler em dados SPHEREx")
    papers.add_argument("--output", default="outputs/literature")
    diff = sub.add_parser("difference", help="Testar diferenciação nas exposições reais SPHEREx")
    diff.add_argument("--output", default="outputs/differencing")
    diff.add_argument("--data-dir", default="data/spherex")
    zogy = sub.add_parser("zogy", help="SEP, astrometria, ePSF, ZOGY e validação estatística")
    zogy.add_argument("--output", default="outputs/zogy")
    zogy.add_argument("--data-dir", default="data/spherex")
    zogy.add_argument("--null-trials", type=int, default=128)
    sprints = sub.add_parser(
        "sprints", help="XGBoost, ranking, associação de movimento e demonstração"
    )
    sprints.add_argument("--output")
    sprints.add_argument("--samples", type=int, default=900)
    sprints.add_argument("--train-timeout", type=float, default=120.0)
    sprints.add_argument("--reuse-training", action="store_true")
    sprints.add_argument(
        "--synthetic-controls",
        action="store_true",
        help="Run the old synthetic-label experiment explicitly",
    )
    observed = sub.add_parser("observed", help="Astroquery: SPHEREx + Gaia e treino observado")
    observed.add_argument("--output", default="outputs/observed")
    observed.add_argument("--train-timeout", type=float, default=120.0)
    observed.add_argument("--reuse-training", action="store_true")
    expand = sub.add_parser("expand", help="Ampliar SPHEREx/Gaia com novos campos e treinar")
    expand.add_argument("--output", default="outputs/expanded")
    expand.add_argument("--per-field", type=int, default=8)
    expand.add_argument("--train-timeout", type=float, default=120.0)
    timelapse = sub.add_parser(
        "timelapse", help="Gerar GIF SPHEREx em épocas completas de seis meses, estilo WiseView"
    )
    timelapse.add_argument("--output", default="outputs/timelapse")
    timelapse.add_argument("--data-dir", default="data/timelapse_fov176as")
    timelapse.add_argument("--ra", type=float, default=133.786245)
    timelapse.add_argument("--dec", type=float, default=-7.244372)
    gaia_timelapse = sub.add_parser(
        "gaia-timelapse", help="Animar posições Gaia DR3 propagadas pelo movimento próprio"
    )
    gaia_timelapse.add_argument("--output", default="outputs/gaia_timelapse")
    gaia_timelapse.add_argument("--data-dir", default="data/gaia_timelapse")
    gaia_timelapse.add_argument("--ra", type=float, default=133.786245)
    gaia_timelapse.add_argument("--dec", type=float, default=-7.244372)
    spectral = sub.add_parser("spectral-cube", help="Espectro, mapa PAH e GIF das bandas do cubo")
    spectral.add_argument("path", help="FITS mosaico 3D com IMAGE, NHITS e WCS-WAVE")
    spectral.add_argument("--output", default="outputs/spectral_cube")
    spectral.add_argument("--label", default="M101")
    temporal = sub.add_parser("temporal-band", help="Animar observações mantendo uma banda fixa")
    temporal.add_argument("--plane", type=int, default=99)
    temporal.add_argument("--inventory", default="outputs/timelapse/observations.csv")
    temporal.add_argument("--channel-cube", default="data/spectral_cube/M101_irsa.fits")
    temporal.add_argument("--output", default="outputs/temporal_band")
    args = parser.parse_args()
    if args.command == "inspect":
        print(json.dumps(inventory_path(args.path), indent=2, ensure_ascii=False))
    elif args.command == "temporal-band":
        from .temporal_band import build_temporal_band

        build_temporal_band(args.inventory, args.channel_cube, args.output, args.plane)
    elif args.command == "spectral-cube":
        from .spectral_cube import build_spectral_cube

        build_spectral_cube(args.path, args.output, args.label)
    elif args.command == "expand":
        from .expanded_training import run_expanded

        run_expanded(args.output, args.per_field, args.train_timeout)
    elif args.command == "timelapse":
        from .time_lapse import build_timelapse

        build_timelapse(args.output, args.data_dir, args.ra, args.dec)
    elif args.command == "gaia-timelapse":
        from .gaia_timelapse import build_gaia_timelapse

        build_gaia_timelapse(args.output, args.data_dir, args.ra, args.dec)
    elif args.command == "observed":
        from .observed_training import run_observed

        run_observed(args.output, args.train_timeout, args.reuse_training)
    elif args.command == "sprints":
        if args.synthetic_controls:
            from .sprints import run_sprints

            run_sprints(
                args.output or "outputs/synthetic_controls",
                args.samples,
                args.train_timeout,
                args.reuse_training,
            )
        else:
            from .observed_training import run_observed

            run_observed(args.output or "outputs/observed", args.train_timeout, args.reuse_training)
    elif args.command == "zogy":
        from .zogy_pipeline import run_pipeline

        run_pipeline(args.output, args.data_dir, args.null_trials)
    elif args.command == "difference":
        from .differencing import run_difference

        run_difference(args.output, args.data_dir)
    elif args.command == "papers":
        from .literature import run_literature

        run_literature(args.output)
    elif args.command == "real":
        from .real_data import run_real

        run_real(args.output, args.data_dir)
    else:
        from .demo import run_demo

        report = run_demo(args.output, args.seed, args.null_trials)
        print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
