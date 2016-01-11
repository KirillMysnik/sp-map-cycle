from commands.say import say_command_manager
from core import AutoUnload
from listeners import OnClientDisconnect
from listeners.tick import Delay
from messages import SayText2


# Anti-spam timeout
ANTI_SPAM_TIMEOUT = 3

# We don't translate this message to avoid extra
# language/translation lookup operations
spam_message = SayText2(message="You're spamming the command")

# This is where Delay instances for each client will be stored at
recent_clients = {}


def _remove_index(index):
    del recent_clients[index]


class NoSpamSayCommand(AutoUnload):
    def __init__(self, names):
        self.names = names
        self.callback = None

    def __call__(self, callback):
        def new_callback(command, index, teamonly):
            if index in recent_clients:
                recent_clients[index].cancel()
                recent_clients[index] = Delay(
                    ANTI_SPAM_TIMEOUT, _remove_index, index)

                spam_message.send(index)
                return

            recent_clients[index] = Delay(
                ANTI_SPAM_TIMEOUT, _remove_index, index)

            callback(command, index, teamonly)

        self.callback = new_callback

        say_command_manager.register_commands(self.names, new_callback)

        return new_callback

    def _unload_instance(self):
        say_command_manager.unregister_commands(self.names, self.callback)


@OnClientDisconnect
def listener_on_client_disconnect(index):
    if index in recent_clients:
        recent_clients[index].cancel()
        del recent_clients[index]
