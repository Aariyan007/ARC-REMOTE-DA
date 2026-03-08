import sys

try:
    import pkg_resources
except ImportError:
    class _MockDistribution:
        def __init__(self, version='2.0.10'):
            self.version = version
    
    class _MockPkgResources:
        def get_distribution(self, name):
            return _MockDistribution()
    
    sys.modules['pkg_resources'] = _MockPkgResources()

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