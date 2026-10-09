"""Punto de entrada ejecutable para la web interna de revisor-crf."""

from __future__ import annotations

import argparse
from dataclasses import replace
import ipaddress

import uvicorn

from .config import config


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Servidor web interno para el revisor de CRF (solo 127.0.0.1 por defecto)."
    )
    parser.add_argument(
        "--host",
        default=config.host,
        help="Dirección IP de enlace (predeterminado: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=config.port,
        help="Puerto TCP de escucha (predeterminado: 8000)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Demostración local sin IIS; sólo se permite en loopback.",
    )
    parser.add_argument(
        "--demo-identity",
        default="demo.local",
        help="Identidad técnica usada exclusivamente por --demo.",
    )
    args = parser.parse_args(argv)

    try:
        loopback = ipaddress.ip_address(args.host).is_loopback
    except ValueError:
        loopback = args.host.casefold() == "localhost"
    if args.demo and not loopback:
        parser.error("--demo sólo puede usarse con 127.0.0.1, ::1 o localhost")

    if args.demo:
        from .app import create_app

        app_config = replace(
            config,
            host=args.host,
            port=args.port,
            demo_mode=True,
            demo_identity=args.demo_identity,
        )
        application = create_app(app_config)
        print("ADVERTENCIA: modo demostración local; no publicar este puerto en la red.")
        print(f"Abra http://{args.host}:{args.port} en esta computadora.")
        uvicorn.run(application, host=args.host, port=args.port, reload=False)
    else:
        print(f"Iniciando servidor web interno en http://{args.host}:{args.port}")
        uvicorn.run("revisor_web.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
