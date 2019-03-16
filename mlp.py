import numpy as np


def _generate_minibatches(X, y, batch_size=32):
    N = len(X)
    assert N == len(y)

    if batch_size == 1:  # standard sgd
        batch_size = 1
        n_batches = N
        last_batch_size = batch_size
    elif batch_size == -1:  # batch sgd
        batch_size = N
        n_batches = 1
        last_batch_size = batch_size
    else:  # minibatch sgd
        n_batches, last_batch_size = divmod(N, batch_size)
        n_batches = n_batches + (1 if last_batch_size > 0 else 0)

    ix = 0

    for batch_i in range(n_batches):
        batch_start = ix
        batch_end = ix + batch_size

        if batch_end > N:
            batch_end = ix + last_batch_size

        yield batch_i, X[batch_start:batch_end], y[batch_start:batch_end]

        ix += batch_size


class Layer:
    def __init__(self, n_inputs, n_units, activation_func, is_output=False):
        self.n_inputs = n_inputs
        self.n_units = n_units
        self.W = np.random.normal(0, 1, (n_inputs, n_units)) * np.sqrt(1.0 / n_inputs)
        self.b = np.random.normal(0, 1, n_units)
        self.prev_dW = np.zeros_like(self.W)
        self.prev_db = np.zeros_like(self.b)
        self.prev_input = None
        self.activation_value = None
        self.preactivation_value = None
        self.activation_func = activation_func
        self.is_output = is_output
        self.network = None
        self.next_layer = None

    def forward(self, X):
        self.prev_input = X

        output = np.matmul(X, self.W) + self.b
        self.preactivation_value = output

        output = self.activation_func(output)
        self.activation_value = output

        return output

    def backward(self, errors):
        N = errors.shape[0]
        delta = np.zeros((N, self.n_units))
        dW = np.zeros((N, *self.W.shape))
        db = np.zeros((N, *self.b.shape))

        if self.is_output:
            for n in range(N):
                for j in range(self.n_units):
                    delta[n, j] = errors[n] * self.activation_func.derivative(self.activation_value[n, j])

                    for i in range(self.n_inputs):
                        dW[n, i, j] = self.network.learning_rate * delta[n, j] * self.prev_input[
                            n, i] + self.network.momentum * self.prev_dW[i, j]
                        db[n, j] = self.network.learning_rate * delta[n, j] + self.network.momentum * self.prev_db[j]

        else:
            for n in range(N):
                for j in range(self.n_units):
                    for k in range(self.next_layer.n_units):
                        delta[n, j] += errors[n, k] * self.next_layer.W[j, k]

                    delta[n, j] *= self.activation_func.derivative(self.activation_value[n, j])

                    for i in range(self.n_inputs):
                        dW[n, i, j] = self.network.learning_rate * delta[n, j] * self.prev_input[
                            n, i] + self.network.momentum * self.prev_dW[i, j]
                        db[n, j] = self.network.learning_rate * delta[n, j] + self.network.momentum * self.prev_db[j]

        self.W += dW.mean(axis=0)
        self.b += db.mean(axis=0)

        self.prev_dW = dW.mean(axis=0)
        self.prev_db = db.mean(axis=0)

        return delta


class MLP:
    def __init__(self, learning_rate=1.0, momemtum=0.9):
        self.learning_rate = learning_rate
        self.momentum = momemtum
        self.layers = []

    def add(self, layer):
        if len(self.layers) > 0:
            self.layers[-1].is_output = False
            self.layers[-1].next_layer = layer

        layer.network = self
        layer.is_output = True
        self.layers.append(layer)

    def forward(self, X):
        output = X

        for layer in self.layers:
            output = layer.forward(output)

        return output

    def backward(self, errors):
        error_grad = errors

        for layer in reversed(self.layers):
            error_grad = layer.backward(error_grad)

    def fit(self, X, y, n_epochs=100, batch_size=-1, early_stopping_threshold=-1, early_stopping_min_improvement=1e-5):
        best_score = 2 ** 31 - 1
        epochs_no_improvement = 0

        for epoch in range(n_epochs):
            epoch_error_history = np.array([])

            for _, X_batch, y_batch in _generate_minibatches(X, y, batch_size):
                target_pred = self.forward(X_batch)
                errors = y_batch - target_pred
                self.backward(errors)
                epoch_error_history = np.append(epoch_error_history, errors)

            rmse = np.sqrt(np.mean(np.square(epoch_error_history)))

            print('Epoch %d of %d - RMSE: %.4f' % (epoch + 1, n_epochs, rmse))

            if best_score - rmse > early_stopping_min_improvement:
                best_score = rmse
                epochs_no_improvement = 0
            else:
                epochs_no_improvement += 1

            if early_stopping_threshold > 0 and epochs_no_improvement > early_stopping_threshold:
                print('Stopping early.')
                break

    def predict_proba(self, X):
        return self.forward(X)

    def predict(self, X):
        return np.argmax(self.predict_proba(X), axis=0)

    def score(self, X, y):
        y_pred = self.predict_proba(X)

        return np.sqrt(np.mean(np.square(y - y_pred)))
