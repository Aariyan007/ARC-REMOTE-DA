from core.listener import start_listener

def assistant_loop():

    while True:

        command = input("Command: ")

        if command == "exit":
            break

        print("Processing:", command)


def main():

    while True:

        activated = start_listener()

        if activated:

            print("Jarvis activated")

            assistant_loop()


if __name__ == "__main__":

    main()