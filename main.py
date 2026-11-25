import asyncio
import sys
from libs.args import parser
from libs.consumer import ConsumerInterface


async def main():
    consumer: ConsumerInterface = None
    args = parser()

    if args.client:
        # Remote desktop client (Kivy, layer images only). Imported here so the
        # web modes don't start Kivy.
        from libs.client import Client
        from libs.gui import Gui

        cli = Client(args)
        await cli.start()
        consumer = Gui(cli)
    else:
        if args.ble:
            from libs.keyboard_ble_hid import KeyboardBLEHID

            keyboard = KeyboardBLEHID()
        else:
            from libs.keyboard_hid import Keyboard

            keyboard = Keyboard(required=args.server)

        if args.server:
            from libs.server import Server

            consumer = Server(keyboard, args)
        else:
            from libs.webserver import WebServer

            if args.web:
                # Reachable from other devices on the network
                consumer = WebServer(keyboard, args, host="0.0.0.0", open_window=args.open)
            else:
                # Local display: same page, localhost only, in an app window
                consumer = WebServer(keyboard, args, host="127.0.0.1", open_window=True)

    try:
        await consumer.start()
    except KeyboardInterrupt:
        if hasattr(consumer, "cleanup"):
            await consumer.cleanup()
        else:
            consumer.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user (Ctrl+C)")
    except SystemExit as e:
        sys.exit(e.code)
