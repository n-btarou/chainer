from chainer.functions.array import broadcast
from chainer.functions.array import concat
from chainer.functions.array import reshape
from chainer.functions.array import select_item
from chainer.functions.array import split_axis
from chainer.functions.connection import embed_id
from chainer.functions.math import logsumexp
from chainer.functions.math import minmax
from chainer.functions.math import sum as _sum


def crf1d(cost, xs, ys):

    """Calculates negative log-likelihood of linear-chain CRF.

    It takes a transition cost matrix, a sequence of costs, and a sequence of
    labels. Let :math:`c_{st}` be a transition cost from a label :math:`s` to
    a label :math:`t`, :math:`x_{it}` be a cost of a label :math:`t` at
    position :math:`i`, and :math:`y_i` be an expected label at position
    :math:`i`. The negative log-likelihood of linear-chain CRF is defined as

    .. math::
        L = -\\left( \\sum_{i=1}^l x_{iy_i} + \\
             \\sum_{i=1}^{l-1} c_{y_i y_{i+1}} - {\\log(Z)} \\right) ,

    where :math:`l` is the length of the input sequence and :math:`Z` is the
    normalizing constant called partition function.

    Args:
        cost (Variable): A :math:`K \\times K` matrix which holds transition
            cost between two labels, where :math:`K` is the number of labels.
        xs (list of Variable): Input feature vector for each label. Each
            :class:`~chainer.Variable` holds a :math:`B \\times K`
            matrix, where :math:`B` is mini-batch size, :math:`K` is the number
            of labels.
        ys (list of Variable): Expected output labels. Each
            :class:`~chainer.Variable` holds a :math:`B` integer vector.

    Returns:
        ~chainer.Variable: A variable holding the average negative
            log-likelihood of the input sequences.

    .. note::

        See detail in the original paper: `Conditional Random Fields:
        Probabilistic Models for Segmenting and Labeling Sequence Data
        <http://repository.upenn.edu/cis_papers/159/>`_.

    """
    assert xs[0].shape[1] == cost.shape[0]

    n_label = cost.shape[0]
    n_batch = xs[0].shape[0]

    alpha = xs[0]
    alphas = []
    for x in xs[1:]:
        batch = x.shape[0]
        if alpha.shape[0] > batch:
            alpha, alpha_rest = split_axis.split_axis(alpha, [batch], axis=0)
            alphas.append(alpha_rest)
        b_alpha, b_cost = broadcast.broadcast(alpha[..., None], cost)
        alpha = logsumexp.logsumexp(b_alpha + b_cost, axis=1) + x

    if len(alphas) > 0:
        alphas.append(alpha)
        alpha = concat.concat(alphas[::-1], axis=0)

    logz = logsumexp.logsumexp(alpha, axis=1)

    cost = reshape.reshape(cost, (cost.size, 1))
    score = select_item.select_item(xs[0], ys[0])
    scores = []
    for x, y, y_prev in zip(xs[1:], ys[1:], ys[:-1]):
        batch = x.shape[0]
        if score.shape[0] > batch:
            y_prev, _ = split_axis.split_axis(y_prev, [batch], axis=0)
            score, score_rest = split_axis.split_axis(score, [batch], axis=0)
            scores.append(score_rest)
        score += (select_item.select_item(x, y)
                  + reshape.reshape(
                      embed_id.embed_id(y_prev * n_label + y, cost), (batch,)))

    if len(scores) > 0:
        scores.append(score)
        score = concat.concat(scores[::-1], axis=0)

    return _sum.sum(logz - score) / n_batch


def argmax_crf1d(cost, xs):
    alpha = xs[0]
    alphas = []
    max_inds = []
    for x in xs[1:]:
        batch = x.shape[0]
        if alpha.shape[0] > batch:
            alpha, alpha_rest = split_axis.split_axis(alpha, [batch], axis=0)
            alphas.append(alpha_rest)
        else:
            alphas.append(None)
        b_alpha, b_cost = broadcast.broadcast(alpha[..., None], cost)
        scores = b_alpha + b_cost
        max_ind = minmax.argmax(scores, axis=1)
        max_inds.append(max_ind)
        alpha = minmax.max(scores, axis=1) + x

    inds = minmax.argmax(alpha, axis=1)
    path = [inds.data]
    for m, a in zip(max_inds[::-1], alphas[::-1]):
        inds = select_item.select_item(m, inds)
        if a is not None:
            inds = concat.concat([inds, minmax.argmax(a, axis=1)], axis=0)
        path.append(inds.data)
    path.reverse()

    score = minmax.max(alpha, axis=1)
    for a in alphas[::-1]:
        if a is None:
            continue
        score = concat.concat([score, minmax.max(a, axis=1)], axis=0)

    return score, path
