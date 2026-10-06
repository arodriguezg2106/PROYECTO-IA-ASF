"""Punto de entrada ejecutable para la web interna de revisor-crf."""

from __future__ import annotations

import argparse
import sys

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
    args = parser.parse_args(argv)

    print(f"Iniciando servidor web interno en http://{args.host}:{args.port}")
    uvicorn.run("revisor_web.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()

