from auth.voice.verify_voice import verify_voice

def start_jarvis():

    print("Jarvis starting...")

    verified = verify_voice()

    if not verified:

        print("Unauthorized speaker. Ignoring.")

        return

    print("Owner verified. Jarvis activated.")

    assistant_loop()


def assistant_loop():

    while True:

        command = input("Command: ")

        if command == "exit":
            break

        print("Processing:", command)


if __name__ == "__main__":

    start_jarvis()