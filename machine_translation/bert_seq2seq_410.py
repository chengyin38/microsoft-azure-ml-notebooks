# -*- coding: utf-8 -*-
"""seq2seq.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1IBquHV3hUXGzB9OdWkx2Y1Ur0msH-LZP

# Setting up
"""

### Mount Google Drive with Colab
# from google.colab import drive
# drive.mount('/content/gdrive')

### Create smaller dataset for troubleshooting
# train_de_r = open('/content/gdrive/My Drive/CS690D Deep Learning for NLP/iwslt16_en_de/train.de', encoding='utf-8').\
#         read().strip().split('\n')
# train_en_r = open('/content/gdrive/My Drive/CS690D Deep Learning for NLP/iwslt16_en_de/train.en', encoding='utf-8').\
#         read().strip().split('\n')
# dev_de_r = open('/content/gdrive/My Drive/CS690D Deep Learning for NLP/iwslt16_en_de/dev.de', encoding='utf-8').\
#         read().strip().split('\n')
# dev_en_r = open('/content/gdrive/My Drive/CS690D Deep Learning for NLP/iwslt16_en_de/dev.en', encoding='utf-8').\
#         read().strip().split('\n')

# train_de_w = open('/content/gdrive/My Drive/CS690D Deep Learning for NLP/small_datasets/train.de.txt', 'w')
# train_en_w = open('/content/gdrive/My Drive/CS690D Deep Learning for NLP/small_datasets/train.en.txt', 'w')
# dev_de_w = open('/content/gdrive/My Drive/CS690D Deep Learning for NLP/small_datasets/dev.de.txt', 'w')
# dev_en_w = open('/content/gdrive/My Drive/CS690D Deep Learning for NLP/small_datasets/dev.en.txt', 'w')

# for line in train_de_r[0:30000]:
#   train_de_w.write(line + '\n')
# train_de_w.close()

# for line in train_en_r[0:30000]:
#   train_en_w.write(line + '\n')
# train_en_w.close()

# for line in dev_de_r[0:1000]:
#   dev_de_w.write(line + '\n')
# dev_de_w.close()

# for line in dev_en_r[0:1000]:
#   dev_en_w.write(line + '\n')
# dev_en_w.close()

import torch
import torch.nn as nn
import torch.optim as optim

from torchtext.datasets import TranslationDataset
from torchtext.data import Field, BucketIterator
# import spacy

import random
import math
import os
import time

### Set random seed for deterministic results
my_seed = 123

random.seed(my_seed)
torch.manual_seed(my_seed)
torch.backends.cudnn.deterministic = True


# for Azure
parser = argparse.ArgumentParser()
parser.add_argument('--data-folder', type=str, dest='data_folder', help='data folder mounting point')
args = parser.parse_args()

data_folder = os.path.join(args.data_folder, 'machine_translation')

"""# Preprocessing data"""

### Download and load spaCy models for each language so we can access the tokenizer of each model 
# !python -m spacy download en
# !python -m spacy download de

# spacy_de = spacy.load('de')
# spacy_en = spacy.load('en')

# Use BERT embedding
from bert_embedding import BertEmbedding
# bert_embedding = BertEmbedding()
# result = bert_embedding(sentences)

bert_embedding = BertEmbedding(model='bert_12_768_12', dataset_name='wiki_multilingual_cased')

spacy_en = bert_embedding
spacy_de = bert_embedding

### Functions to tokenize text from a string into a list of tokens 
def tokenize_de(text):
  # reverse the order of input tokens as suggested by reference paper
  return [tok for tok in spacy_de.tokenizer(text)][::-1]

def tokenize_en(text):
  return [tok for tok in spacy_en.tokenizer(text)]

### Handle how data should be processed 
### (get correct tokenization for each language, append <sos> & <eos>,
### convert all words to lowercase)
src = Field(tokenize=tokenize_de, init_token='<sos>', eos_token='<eos>', lower=True)
trg = Field(tokenize=tokenize_en, init_token='<sos>', eos_token='<eos>', lower=True)

### Use this for the entire dataset
# train_data = TranslationDataset(path='/content/gdrive/My Drive/CS690D Deep Learning for NLP/iwslt16_en_de/train',
#                                         exts=('.de', '.en'), fields=(src, trg))
# dev_data = TranslationDataset(path='/content/gdrive/My Drive/CS690D Deep Learning for NLP/iwslt16_en_de/dev',
#                                         exts=('.de', '.en'), fields=(src, trg))

# for Azure
train_data = TranslationDataset(path=os.path.join(data_folder, 'train'),
                                         exts=('.de', '.en'), fields=(src, trg))
dev_data = TranslationDataset(path=os.path.join(data_folder, 'dev'),
                                     exts=('.de', '.en'), fields=(src, trg))

### Convert text files into TranslationDataset type of torchtext --- this is the small dataset
# train_data = TranslationDataset(path='/content/gdrive/My Drive/CS690D Deep Learning for NLP/small_datasets/train',
#                                         exts=('.de', '.en'), fields=(src, trg))
# dev_data = TranslationDataset(path='/content/gdrive/My Drive/CS690D Deep Learning for NLP/small_datasets/dev',
#                                         exts=('.de', '.en'), fields=(src, trg))

print(f"Number of training examples: {len(train_data.examples)}")
print(f"Number of validation examples: {len(dev_data.examples)}")
print(vars(train_data.examples[1]))

### Remove examples whose length of target sentences exceed 25 words
for i, example in enumerate(train_data.examples):
  if len(getattr(train_data.examples[i], 'trg')) > 25:
    del train_data.examples[i]

for i, example in enumerate(dev_data.examples):
  if len(getattr(dev_data.examples[i], 'trg')) > 25:
    del dev_data.examples[i]

print(f"Number of training examples: {len(train_data.examples)}")
print(f"Number of validation examples: {len(dev_data.examples)}")
print(vars(train_data.examples[20000]))

### Build vocabulary based on trainings set only to prevent information leakage
### Only tokens that appear at least twice can be added to vocabulary 
### Tokens that appear only once are converted into <unk> token. 
src.build_vocab(train_data, min_freq=10)
trg.build_vocab(train_data, min_freq=10)

print(f"Unique tokens in source (de) vocabulary: {len(src.vocab)}")
print(f"Unique tokens in target (en) vocabulary: {len(trg.vocab)}")

# device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
bsz = 64

### Create batches of examples so that all of the source sentences are padded 
### to the same length as the target sentences
train_iterator, dev_iterator = BucketIterator.splits((train_data, dev_data), batch_size=bsz)


"""# Neural seq2seq model"""

class Encoder(nn.Module):
  def __init__(self, input_dim, emb_dim, hid_dim, n_layers, dropout): 
    super().__init__()
    
    self.input_dim = input_dim
    self.emb_dim = emb_dim
    self.hid_dim = hid_dim
    self.n_layers = n_layers
    self.dropout = dropout
    
    self.embedding = nn.Embedding(input_dim, emb_dim)
    
    self.rnn = nn.LSTM(emb_dim, hid_dim, n_layers, dropout=dropout)
    
    self.dropout = nn.Dropout(dropout)
    
  
  def forward(self, src):
    # src = [src sent len, bsz]
    # embedded = [src sent len, bsz, emb dim]
    embedded = self.dropout(self.embedding(src))
    
    # outputs = [src sent len, bsz, hid dim * n directions]
    # hidden = [n layers, bsz, hid dim]
    # cell = [n layers, bsz, hid dim]
    outputs, (hidden, cell) = self.rnn(embedded) 
    
    # outputs are always from the top hidden layer
    
    return hidden, cell

class Decoder(nn.Module):
  def __init__(self, output_dim, emb_dim, hid_dim, n_layers, dropout):
    super().__init__()
    
    self.emb_dim = emb_dim
    self.hid_dim = hid_dim
    self.output_dim = output_dim
    self.n_layers = n_layers
    self.dropout = dropout
    
    self.embedding = nn.Embedding(output_dim, emb_dim)
    
    self.rnn = nn.LSTM(emb_dim, hid_dim, n_layers, dropout=dropout)
    
    self.out = nn.Linear(hid_dim, output_dim)
    
    self.dropout = nn.Dropout(dropout)
    
  def forward(self, input, hidden, cell):
    # input = [1, bsz] (after adding fake dimension)
    input = input.unsqueeze(0) 
    
    # embedded = [1, bsz, emb dim]
    embedded = self.dropout(self.embedding(input))
    
    # output = [sent len, bsz, hid dim]
    # hidden = [n layers, bsz, hid dim]
    # cell = [n layers, bsz, hid dim]
    output, (hidden, cell) = self.rnn(embedded, (hidden, cell))
    
    # prediction = [bsz, output dim]
    prediction = self.out(output.squeeze(0))
    
    return prediction, hidden, cell

class Seq2Seq(nn.Module):
  def __init__(self, encoder, decoder):

    super().__init__()
    
    self.encoder = encoder
    self.decoder = decoder
    # self.device = device
    
    # hidden dim of encoder and decoder must be equal
    assert encoder.hid_dim == decoder.hid_dim
    # encoder and decoder must have same number of layers
    assert encoder.n_layers == decoder.n_layers
    
  def forward(self, src, trg, teacher_forcing_ratio=0.5):
    # src = [src sent len, bsz]
    # trg = [trg sent len, bsz]
    batch_size = trg.shape[1]
    max_len = trg.shape[0]
    trg_vocab_size = self.decoder.output_dim
    
    # tensor to store decoder outputs
    outputs = torch.zeros(max_len, batch_size, trg_vocab_size)
    
    # last hidden state of the encoder is used as the initial hidden state of the decoder
    hidden, cell = self.encoder(src)
    
    # first input to the decoder is the <sos> tokens
    input = trg[0,:]
    
    for t in range(1, max_len):
      output, hidden, cell = self.decoder(input, hidden, cell)
      outputs[t] = output
      teacher_force = random.random() < teacher_forcing_ratio
      top1 = output.max(1)[1]
      # teacher_forcing_ratio is probability to use teacher forcing
      # eg. if teacher_forcing_ratio=0.75, we use ground-truth inputs 75% of the 
      # time and the previous predicted output 25% of time
      input = (trg[t] if teacher_force else top1)
      
    return outputs

"""# Training the model"""

input_dim = len(src.vocab)
output_dim = len(trg.vocab)
enc_emb_dim = 256
dec_emb_dim = 256
hid_dim = 512
n_layers = 2
enc_dropout = 0.5
dec_dropout = 0.5

enc = Encoder(input_dim, enc_emb_dim, hid_dim, n_layers, enc_dropout)
dec = Decoder(output_dim, dec_emb_dim, hid_dim, n_layers, dec_dropout)

model = Seq2Seq(enc, dec)

def count_parameters(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)

print(f'The model has {count_parameters(model):,} trainable parameters')

### Define optimizer and loss function
optimizer = optim.Adam(model.parameters())

pad_idx = trg.vocab.stoi['<pad>']
criterion = nn.CrossEntropyLoss(ignore_index=pad_idx)

def train(model, iterator, optimizer, criterion, clip):
  model.train()

  epoch_loss = 0
  
  for i, batch in enumerate(iterator):
    src = batch.src
    trg = batch.trg
        
    output = model(src, trg)
    
    # trg = [trg sent len, bsz]
    # output = [trg sent len, bsz, output dim]
    output = output[1:].view(-1, output.shape[-1])
    trg = trg[1:].view(-1)
    
    # trg = [(trg sent len - 1) * bsz]
    # output = [(trg sent len - 1) * bsz, output dim]
    loss = criterion(output, trg)
    loss.backward()
    
    torch.nn.utils.clip_grad_norm_(model.parameters(), clip)
    
    optimizer.step()
    optimizer.zero_grad()
    
    print(i, batch, loss)
    
    epoch_loss += loss.item()
    
    torch.cuda.empty_cache()
    
  return epoch_loss / len(iterator)

def evaluate(model, iterator, criterion):
  model.eval()
  epoch_loss = 0
  with torch.no_grad():
    for i, batch in enumerate(iterator):
      src = batch.src
      trg = batch.trg
      
      # turn off teacher forcing
      output = model(src, trg, 0)
      
      output = output[1:].view(-1, output.shape[-1])
      trg = trg[1:].view(-1)
      
      loss = criterion(output, trg)
      
      epoch_loss += loss.item()
      
  return epoch_loss / len(iterator)

def epoch_time(start_time, end_time):
  elapsed_time = end_time - start_time
  elapsed_mins = int(elapsed_time / 60)
  elapsed_secs = int(elapsed_time - (elapsed_mins * 60))
  return elapsed_mins, elapsed_secs

n_epochs = 10
clip = 1
# save_dir = '/content/gdrive/My Drive/CS690D Deep Learning for NLP/models'
# model_save_path = os.path.join(save_dir, 'neural-seq2seq.pt')
# print(model_save_path)

best_dev_loss = float('inf')

for epoch in range(n_epochs):
  start_time = time.time()
  
  train_loss = train(model, train_iterator, optimizer, criterion, clip)
  dev_loss = evaluate(model, dev_iterator, criterion)
  
  end_time = time.time()
  
  epoch_mins, epoch_secs = epoch_time(start_time, end_time)
  
  if dev_loss < best_dev_loss:
     best_dev_loss = dev_loss
  
  print(f'Epoch: {epoch+1:02} | Time: {epoch_mins}m {epoch_secs}s')
  print(f'\tTrain Loss: {train_loss:.3f} | Train PPL: {math.exp(train_loss):7.3f}')
  print(f'\t Dev. Loss: {dev_loss:.3f} |  Dev. PPL: {math.exp(dev_loss):7.3f}')

# save model 

# torch.save(model.state_dict(), model_save_path)
# print('saved')

# save_dir = '/content/gdrive/My Drive/CS690D Deep Learning for NLP/models'
# model_save_path = os.path.join(save_dir, 'neural-seq2seq-all.pt')


# note that this method is for train on GPU, load on GPU
# # device = torch.device("cuda")
# model.load_state_dict(torch.load(model_save_path))
# model.to(device)

# def predict_sequence(model, tokenizer, source):
# 	prediction = model.predict(source, verbose=0)[0]
# 	integers = [argmax(vector) for vector in prediction]
# 	target = list()
# 	for i in integers:
# 		word = word_for_id(i, tokenizer)
# 		if word is None:
# 			break
# 		target.append(word)
# 	return ' '.join(target)

# translation = predict_sequence(model, spacy_en, dev_data)