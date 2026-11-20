"""Entry point used by the AppImage: handles root/CLI modes before touching Qt."""
import sys


def main():
    args = sys.argv[1:]
    if args[:1] == ["--system-setup"]:
        from . import sysetup
        return sysetup.run_cli()
    if args[:1] == ["--cli"]:
        from . import cli
        return cli.main(args[1:])
    if args[:1] in (["--version"], ["-V"]):
        from . import __version__
        print("IPSec VPN - Design By Rashid", __version__)
        return 0
    from . import qt_app
    return qt_app.main(args)


if __name__ == "__main__":
    sys.exit(main())
