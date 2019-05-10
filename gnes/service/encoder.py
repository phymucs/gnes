#  Tencent is pleased to support the open source community by making GNES available.
#
#  Copyright (C) 2019 THL A29 Limited, a Tencent company. All rights reserved.
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

# pylint: disable=low-comment-ratio

import zmq

from .base import BaseService as BS, ComponentNotLoad, ServiceMode, ServiceError, MessageHandler
from ..document import MultiSentDocument, DocumentMapper, UniSentDocument
from ..messaging import *
from ..proto import gnes_pb2, array2blob, blob2array


class EncoderService(BS):
    handler = MessageHandler(BS.handler)

    def _post_init(self):
        from ..encoder.base import PipelineEncoder

        self._model = None
        try:
            self._model = PipelineEncoder.load(self.args.dump_path)
            self.logger.info('load a trained encoder')
        except FileNotFoundError:
            if self.args.mode == ServiceMode.TRAIN:
                try:
                    self._model = PipelineEncoder.load_yaml(
                        self.args.yaml_path)
                    self.logger.info(
                        'load an uninitialized encoder, training is needed!')
                except FileNotFoundError:
                    raise ComponentNotLoad
            else:
                raise ComponentNotLoad

    def _raise_empty_model_error(self):
        raise ValueError('no model config available, exit!')

    @handler.register(MessageType.DEFAULT.name)
    def _handler_default(self, msg: 'gnes_pb2.Message', out: 'zmq.Socket'):
        chunks = []
        chunks_num = []
        for doc in msg.docs:
            chunks_num.append(doc.doc_size)
            if msg.doc_type == gnes_pb2.Document.TEXT_DOC:
                chunks.extend(doc.text_chunks)
            elif msg.doc_type == gnes_pb2.Document.IMAGE_DOC:
                chunks.extend(doc.blob_chunks)
            else:
                raise NotImplemented()

        if msg.mode == gnes_pb2.Message.TRAIN:
            self.logger.info('the length of chunks is {}'.format(len(chunks)))
            self.logger.info('\n'.join(chunks))
            self._model.train(chunks)
            self.is_model_changed.set()

        elif msg.mode == gnes_pb2.Message.INDEX:
            vecs = self._model.encode(chunks)
            self.logger.info('vecs shape {}'.format(vecs.shape))
            self.logger.info('chunks size {}'.format(len(chunks)))
            assert len(vecs) == len(chunks)
            start = 0
            for i, doc in enumerate(msg.docs):
                x = vecs[start:start+chunks_num[i]]
                doc.encodes.CopyFrom(array2blob(x))
                doc.is_encoded = True
                start += chunks_num[i]

            msg.is_encoded = True
            send_message(out, msg, self.args.timeout)

        elif msg.mode == gnes_pb2.Message.QUERY:
            vecs = self._model.encode(chunks)
            assert len(vecs) == len(chunks)
            num_querys = len(msg.querys)
            assert num_querys == len(vecs)
            msg.docs[0].encodes.CopyFrom(array2blob(vecs))
            doc.is_encoded = True

            msg.is_encoded = True
            send_message(out, msg, self.args.timeout)
        else:
            raise ServiceError('service %s runs in unknown mode %s' %
                               (self.__class__.__name__, self.args.mode))
