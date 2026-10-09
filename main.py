"""SliceCam - camera-controlled fruit slicing game.   Run with:  python main.py"""
import sys
import traceback


def main() -> int:
    try:
        from game.game import Game
    except ImportError as exc:
        print(f"Missing dependency: {exc}\nRun:  pip install -r requirements.txt")
        return 1
    try:
        Game().run()
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
