"""Compatibility entry point for the graphical offline installer builder.

The former source ZIP installer opened console windows and could be extracted or
run from Desktop. Keep the command name for existing automation while routing
all future packages through the single windowed installer pipeline.
"""

from build_desktop_exe import main


if __name__ == '__main__':
    main()
