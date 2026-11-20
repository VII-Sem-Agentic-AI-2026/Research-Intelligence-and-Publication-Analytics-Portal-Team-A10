"""Standalone server bootstrap. All product operations live in the dashboard."""
import argparse
from .web import serve

def main(argv=None):
    parser=argparse.ArgumentParser(description="Start the standalone Research Intelligence Agent dashboard")
    parser.add_argument("serve", nargs="?", default="serve")
    parser.add_argument("--port", type=int, default=8001)
    args=parser.parse_args(argv)
    serve(args.port)

if __name__ == "__main__": main()
