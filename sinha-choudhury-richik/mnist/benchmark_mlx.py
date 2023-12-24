# Copyright © 2023 Apple Inc.

import argparse
import time

import numpy as np

import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim

import mnist

from benchmark import TrainBenchmark, TestBenchmark


class MLP(nn.Module):
    """A simple MLP."""

    def __init__(
        self, num_layers: int, input_dim: int, hidden_dim: int, output_dim: int
    ):
        super().__init__()
        layer_sizes = [input_dim] + [hidden_dim] * num_layers + [output_dim]
        self.layers = [
            nn.Linear(idim, odim)
            for idim, odim in zip(layer_sizes[:-1], layer_sizes[1:])
        ]

    def __call__(self, x):
        for l in self.layers[:-1]:
            x = mx.maximum(l(x), 0.0)
        return self.layers[-1](x)


def loss_fn(model, X, y):
    return mx.mean(nn.losses.cross_entropy(model(X), y))


def eval_fn(model, X, y):
    return mx.mean(mx.argmax(model(X), axis=1) == y)


def batch_iterate(batch_size, X, y):
    perm = mx.array(np.random.permutation(y.size))
    for s in range(0, y.size, batch_size):
        ids = perm[s : s + batch_size]
        yield X[ids], y[ids]


def main(num_iters, num_epochs=10, vary_batch_size=False):
    seed = 0
    num_layers = 2
    hidden_dim = 32
    num_classes = 10
    init_batch_size = 16 if vary_batch_size else 256

    learning_rate = 1e-1

    np.random.seed(seed)

    # Load the data
    train_images, train_labels, test_images, test_labels = map(mx.array, mnist.mnist())

    benchmark_train = TrainBenchmark(init_batch_size, vary_batch_size, num_iters)

    for _, batch_size in benchmark_train:
        # Load the model
        model = MLP(num_layers, train_images.shape[-1], hidden_dim, num_classes)
        mx.eval(model.parameters())

        loss_and_grad_fn = nn.value_and_grad(model, loss_fn)
        optimizer = optim.SGD(learning_rate=learning_rate)

        for e in range(num_epochs):
            tic = time.perf_counter()
            for X, y in batch_iterate(batch_size, train_images, train_labels):
                loss, grads = loss_and_grad_fn(model, X, y)
                optimizer.update(model, grads)
                mx.eval(model.parameters(), optimizer.state)
            accuracy = eval_fn(model, test_images, test_labels)
            toc = time.perf_counter()
            benchmark_train.add_epoch(toc - tic)
            print(
                f"Epoch {e}: Test accuracy {accuracy.item():.3f},"
                f" Time {toc - tic:.3f} (s)"
            )

    benchmark_test = TestBenchmark(num_iters)

    for i in benchmark_test:
        accuracy = eval_fn(model, test_images, test_labels)
        print(f"Iteration {i}: Test accuracy {accuracy.item():.3f}")

    device = mx.default_device().type
    benchmark_train.write_to_csv(f'results/mlx-train-{device}-n{num_iters}-e{num_epochs}{"-vbatch" if vary_batch_size else ""}.csv')
    benchmark_test.write_to_csv(f'results/mlx-test-{device}-n{num_iters}.csv')


if __name__ == "__main__":
    parser = argparse.ArgumentParser("Train a simple MLP on MNIST with MLX.")
    parser.add_argument("--gpu", action="store_true", help="Use the Metal back-end.")
    parser.add_argument("-n", type=int, default=10, help="Number of benchmark iterations.")
    parser.add_argument("-e", type=int, default=10, help="Number of training epochs per iteration.")
    parser.add_argument("--batch-size", action="store_true", help="Double batch size every iteration.")
    args = parser.parse_args()
    if not args.gpu:
        mx.set_default_device(mx.cpu)
    main(args.n, num_epochs=args.e, vary_batch_size=args.batch_size)
