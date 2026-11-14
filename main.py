from fapello.ui import run_interactive

if __name__ == "__main__":
    try:
        run_interactive()
    except KeyboardInterrupt:
        print("\n\n[Operation cancelled by user]")
    except Exception as e:
        print(f"\n[An unexpected error occurred]: {e}")
