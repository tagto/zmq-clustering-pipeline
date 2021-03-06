import multiprocessing
import zmq
import zlib
import pickle
import numpy as np
from typing import Any


"""
zmqhelpers.py
Helper functions using the zmq library.
Also integrates numpy objects.
"""

TERMINATE = b'TERMINATE'
ARRAY = b'ARRAY'
MODEL = b'MODEL'


class EnableTermination:
    @staticmethod
    def check_termination(s: bytes):
        """Checks if s is the termination message."""
        return s == TERMINATE


class ZMQProxy(multiprocessing.Process, EnableTermination):
    """
    Base class for a ventilator node using a 0MQ SUB interface to listen
    for messages that are then PUSHed to workers.
    """
    __slots__ = ('workers', 'send', 'recv', 'host', 'send_type')

    def __init__(self, workers: int, send: int=5558, recv: int=5557, host: str='127.0.0.1', send_type: int=zmq.PUSH):
        """
        Creates a new ZMQVent that subs and pushes on the given ports.

        :param workers: Number of workers this vent will push to.
        :param send: Port to send on. Defaults to 5558.
        :param recv: Port to receive on. Defaults to 5557.
        :param send_type: ZMQ socket type to send with. Defaults to PUSH.
        """
        super(ZMQProxy, self).__init__()
        self.workers = workers
        self.send = send
        self.send_type = send_type
        self.recv = recv
        self.host = host

    def run(self): 
        """Starts the ventilator."""
        print('Starting ZMQVent')
        context = zmq.Context()
        ventilator = context.socket(self.send_type)
        receiver = context.socket(zmq.XSUB)

        ventilator.bind(f'tcp://*:{self.send}')
        receiver.bind(f'tcp://*:{self.recv}')

        # send a 1 byte to the XSUB so that it subscribes to ALL messages.
        receiver.send(bytes([1]))
        print(f'Ventilator listening on {self.recv}')
        print(f'Ventilator sending on {self.send}')

        while True:
            msg = receiver.recv()

            if not self.check_termination(msg):
                ventilator.send(msg)
            else:
                for i in range(self.workers):
                    ventilator.send(msg)
                receiver.close()
                ventilator.close()
                break


def recv_zipped_pickle(socket: zmq.Socket, flags: int=0):
    """
    Receive a sent zipped pickle.
    """
    message = socket.recv(flags)
    object = zlib.decompress(message)
    return pickle.loads(object)


def send_zipped_pickle(socket: zmq.Socket, obj: Any, flags: int=0, protocol: int=-1):
    """
    Pickle an object, and zip the pickle before sending it
    """
    object = pickle.dumps(obj, protocol)
    compressed_object = zlib.compress(object)
    return socket.send(compressed_object, flags=flags)


def send_array(socket: zmq.Socket, array: np.array, flags: int=0, copy: bool=True, track: bool=False):
    """
    Send a numpy array with metadata, type and shape
    """
    dictionary = dict(
        dtype = str(array.dtype),
        shape = array.shape,
    )
    socket.send_json(dictionary, flags|zmq.SNDMORE)
    return socket.send(array, flags, copy=copy, track=track)


def recv_array(socket: zmq.Socket, flags: int=0, copy: int=True, track: bool=False):
    """
    Recieve a numpy array
    """
    dictionary = socket.recv_json(flags=flags)
    message = socket.recv(flags=flags, copy=copy, track=track)
    buffer = memoryview(message)
    array = np.frombuffer(buffer, dtype=dictionary['dtype'])
    return array.reshape(dictionary['shape'])
