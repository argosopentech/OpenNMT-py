import copy
import unittest
import torch
import pyonmttok
from onmt.constants import DefaultTokens
from collections import Counter
import onmt
import onmt.inputters
import onmt.opts
from onmt.model_builder import build_embeddings, \
    build_encoder, build_decoder
from onmt.utils.parse import ArgumentParser

parser = ArgumentParser(description='train.py')
onmt.opts.model_opts(parser)
onmt.opts._add_train_general_opts(parser)

# -data option is required, but not used in this test, so dummy.
opt = parser.parse_known_args(['-data', 'dummy'])[0]


class TestModel(unittest.TestCase):

    def __init__(self, *args, **kwargs):
        super(TestModel, self).__init__(*args, **kwargs)
        self.opt = opt

    def get_vocabs(self):
        src_vocab = pyonmttok.build_vocab_from_tokens(
            Counter(),
            maximum_size=0,
            minimum_frequency=1,
            special_tokens=[DefaultTokens.UNK,
                            DefaultTokens.PAD,
                            DefaultTokens.BOS,
                            DefaultTokens.EOS])

        tgt_vocab = pyonmttok.build_vocab_from_tokens(
            Counter(),
            maximum_size=0,
            minimum_frequency=1,
            special_tokens=[DefaultTokens.UNK,
                            DefaultTokens.PAD,
                            DefaultTokens.BOS,
                            DefaultTokens.EOS])

        vocabs = {'src': src_vocab, 'tgt': tgt_vocab}
        return vocabs

    def get_batch(self, source_l=3, bsize=1):
        # len x batch x nfeat
        test_src = torch.ones(bsize, source_l, 1).long()
        test_tgt = torch.ones(bsize, source_l, 1).long()
        test_length = torch.ones(bsize).fill_(source_l).long()
        return test_src, test_tgt, test_length

    def embeddings_forward(self, opt, source_l=3, bsize=1):
        '''
        Tests if the embeddings works as expected

        args:
            opt: set of options
            source_l: Length of generated input sentence
            bsize: Batchsize of generated input
        '''
        vocabs = self.get_vocabs()
        emb = build_embeddings(opt, vocabs)
        test_src, _, __ = self.get_batch(source_l=source_l, bsize=bsize)
        if opt.decoder_type == 'transformer':
            input = torch.cat([test_src, test_src], 1)
            res = emb(input)
            compare_to = torch.zeros(bsize, source_l * 2,
                                     opt.src_word_vec_size)
        else:
            res = emb(test_src)
            compare_to = torch.zeros(bsize, source_l, opt.src_word_vec_size)

        self.assertEqual(res.size(), compare_to.size())

    def encoder_forward(self, opt, source_l=3, bsize=1):
        '''
        Tests if the encoder works as expected

        args:
            opt: set of options
            source_l: Length of generated input sentence
            bsize: Batchsize of generated input
        '''
        if opt.hidden_size > 0:
            opt.enc_hid_size = opt.hidden_size
        vocabs = self.get_vocabs()
        embeddings = build_embeddings(opt, vocabs)
        enc = build_encoder(opt, embeddings)

        test_src, test_tgt, test_length = self.get_batch(source_l=source_l,
                                                         bsize=bsize)

        enc_out, hidden_t, test_length = enc(test_src, test_length)

        # Initialize vectors to compare size with
        test_hid = torch.zeros(self.opt.enc_layers, bsize, opt.enc_hid_size)
        test_out = torch.zeros(bsize, source_l, opt.dec_hid_size)

        # Ensure correct sizes and types
        self.assertEqual(test_hid.size(),
                         hidden_t[0].size(),
                         hidden_t[1].size())
        self.assertEqual(test_out.size(), enc_out.size())
        self.assertEqual(type(enc_out), torch.Tensor)

    def nmtmodel_forward(self, opt, source_l=3, bsize=1):
        """
        Creates a nmtmodel with a custom opt function.
        Forwards a testbatch and checks output size.

        Args:
            opt: Namespace with options
            source_l: length of input sequence
            bsize: batchsize
        """
        if opt.hidden_size > 0:
            opt.enc_hid_size = opt.hidden_size
            opt.dec_hid_size = opt.hidden_size
        vocabs = self.get_vocabs()

        embeddings = build_embeddings(opt, vocabs)
        enc = build_encoder(opt, embeddings)

        embeddings = build_embeddings(opt, vocabs, for_encoder=False)
        dec = build_decoder(opt, embeddings)

        model = onmt.models.model.NMTModel(enc, dec)

        test_src, test_tgt, test_length = self.get_batch(source_l=source_l,
                                                         bsize=bsize)
        output, attn = model(test_src, test_tgt, test_length)
        outputsize = torch.zeros(bsize, source_l - 1, opt.dec_hid_size)
        # Make sure that output has the correct size and type
        self.assertEqual(output.size(), outputsize.size())
        self.assertEqual(type(output), torch.Tensor)


def _add_test(param_setting, methodname):
    """
    Adds a Test to TestModel according to settings

    Args:
        param_setting: list of tuples of (param, setting)
        methodname: name of the method that gets called
    """

    def test_method(self):
        opt = copy.deepcopy(self.opt)
        if param_setting:
            for param, setting in param_setting:
                setattr(opt, param, setting)
        ArgumentParser.update_model_opts(opt)
        getattr(self, methodname)(opt)
    if param_setting:
        name = 'test_' + methodname + "_" + "_".join(
            str(param_setting).split())
    else:
        name = 'test_' + methodname + '_standard'
    setattr(TestModel, name, test_method)
    test_method.__name__ = name


'''
TEST PARAMETERS
'''
opt.brnn = False

test_embeddings = [[],
                   [('decoder_type', 'transformer')]
                   ]

for p in test_embeddings:
    _add_test(p, 'embeddings_forward')

tests_encoder = [[],
                 [('encoder_type', 'mean')],
                 # [('encoder_type', 'transformer'),
                 # ('word_vec_size', 16), ('hidden_size', 16)],
                 []
                 ]

for p in tests_encoder:
    _add_test(p, 'encoder_forward')

tests_nmtmodel = [[('rnn_type', 'GRU')],
                  [('layers', 10)],
                  [('input_feed', 0)],
                  [('decoder_type', 'transformer'),
                   ('encoder_type', 'transformer'),
                   ('src_word_vec_size', 16),
                   ('tgt_word_vec_size', 16),
                   ('hidden_size', 16)],
                  [('decoder_type', 'transformer'),
                   ('encoder_type', 'transformer'),
                   ('src_word_vec_size', 16),
                   ('tgt_word_vec_size', 16),
                   ('hidden_size', 16),
                   ('position_encoding', True)],
                  [('coverage_attn', True)],
                  [('copy_attn', True)],
                  [('global_attention', 'mlp')],
                  [('context_gate', 'both')],
                  [('context_gate', 'target')],
                  [('context_gate', 'source')],
                  [('encoder_type', "brnn"),
                   ('brnn_merge', 'sum')],
                  [('encoder_type', "brnn")],
                  [('decoder_type', 'cnn'),
                   ('encoder_type', 'cnn')],
                  [('encoder_type', 'rnn'),
                   ('global_attention', None)],
                  [('encoder_type', 'rnn'),
                   ('global_attention', None),
                   ('copy_attn', True),
                   ('copy_attn_type', 'general')],
                  [('encoder_type', 'rnn'),
                   ('global_attention', 'mlp'),
                   ('copy_attn', True),
                   ('copy_attn_type', 'general')],
                  [],
                  ]

if onmt.models.sru.check_sru_requirement():
    #   """ Only do SRU test if requirment is safisfied. """
    # SRU doesn't support input_feed.
    tests_nmtmodel.append([('rnn_type', 'SRU'), ('input_feed', 0)])

for p in tests_nmtmodel:
    _add_test(p, 'nmtmodel_forward')
