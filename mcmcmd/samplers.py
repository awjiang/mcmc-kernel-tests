import numpy as onp
# import jax.numpy as jnp
import scipy
import multiprocessing
from functools import reduce
from itertools import repeat
import pdb

#######################################################################
######################### Helper Functions ############################
#######################################################################

def XTX(X):
    return X.T @ X

def XTWX(X, W): 
    return X.T @ W @ X

'''
Construct a diagonal matrix with diagonal `z`
'''
def diagMatrix(z):
    diag_z = onp.eye(len(z))
    onp.fill_diagonal(diag_z,z)
    return(diag_z)

'''
Returns a matrix with column means corresponding to the first and second empirical moments of `samples`.
'''
def geweke_functions(samples):
    f1 = samples.copy()
    n, p = f1.shape
    f2 = onp.empty([n, int(p*(p+1)/2)])
    counter = 0
    for i in range(p):
        for j in range(i+1):
            f2[:, counter] = f1[:, i] * f1[:, j]
            counter += 1
    return onp.hstack([f1, f2])
    
'''
If x is a numpy array, return f(x), otherwise return x as a scalar or array
'''
def f_if_array(f, x, return_array=False):
    if type(x).__name__ == 'ndarray':
        if len(x.shape) == 2:
            return f(x)
        elif len(x.shape) < 2:
            assert x.shape[0] == 1
            if return_array==False:
                return float(x)
            else:
                return onp.array(x).reshape(1,1)
        else:
            raise ValueError
    else:
        if return_array==False:
            return float(x)
        else:
            return onp.array(x).reshape(1,1)

def diag(x, return_array=False):
    return f_if_array(onp.diag, x, return_array)

def trace(x, return_array=False):
    return f_if_array(onp.trace, x, return_array)

def det(x, return_array=False):
    return f_if_array(onp.linalg.det, x, return_array)

def logdet(x, return_array=False):
    return onp.log(det(x, return_array))

def inv(x, return_array=False):
    if type(x).__name__ == 'ndarray':
        if len(x.shape) == 2:
            return onp.linalg.inv(x)
        elif len(x.shape) < 2:
            assert x.shape[0] == 1
            if return_array==False:
                return 1./float(x)
            else:
                return onp.array(1./float(x)).reshape(1,1)
        else:
            raise ValueError
    else:
        if return_array==False:
            return 1./float(x)
        else:
            return onp.array(1./float(x)).reshape(1,1)

def array_to_float(x):
    assert type(x).__name__ == 'ndarray'
    if onp.array(x.shape).prod() == 1:
        return float(x)
    else:
        return x

def square_dim(x):
    if type(x).__name__ == 'ndarray':
        if len(x.shape) == 2:
            assert x.shape[0] == x.shape[1]
            dim = x.shape[0]
        elif len(x.shape) == 1:
            assert x.shape[0] == 1
            dim = x.shape[0]
        elif len(x.shape) == 0:
            dim = 1
    else:
        dim = 1
    return dim

'''
Calculate mean and variance of the product of multivariate Gaussians
'''
def GaussianProductMV(mu_0, Sigma_0, lst_mu, lst_Sigma):
    assert(len(lst_mu) == len(lst_Sigma))
    mu_pr, Sigma_pr = mu_0, Sigma_0
    Sigma_pr_shape = onp.array(Sigma_pr).shape
    if Sigma_pr_shape == ():
        d = 1
    else:
        d = Sigma_pr_shape[0]
    for i in range(len(lst_mu)):
        if d == 1:
            mu_pr = (mu_pr*lst_Sigma[i] + lst_mu[i]*Sigma_pr)/(lst_Sigma[i] + Sigma_pr)
            Sigma_pr = (Sigma_pr*lst_Sigma[i])/(Sigma_pr + lst_Sigma[i])
        else:
            # Cholesky
            Sigma_sum = Sigma_pr + lst_Sigma[i]
            L = onp.linalg.cholesky(Sigma_sum)
            Sigma_1 = onp.linalg.solve(L, Sigma_pr)
            Sigma_2 = onp.linalg.solve(L, lst_Sigma[i])
            mu_1= onp.linalg.solve(L, mu_pr.reshape(-1, 1))
            mu_2 = onp.linalg.solve(L, lst_mu[i].reshape(-1, 1))
            mu_pr = Sigma_2.T @ mu_1 + Sigma_1.T @ mu_2
            Sigma_pr = Sigma_1.T @ Sigma_2
    return mu_pr, Sigma_pr

''' 
Split `num_iter` iterations into `nproc` chunks for multithreading
'''
def splitIter(num_iter, nproc):
    arr_iter = (onp.zeros(nproc) + num_iter // nproc).astype('int')
    for i in range(num_iter % nproc):
        arr_iter[i] += 1
    return arr_iter

#######################################################################
############################# Distributions ###########################
#######################################################################

class invwishart_distr(object):
    def __init__(self, df, scale, rng=None):
        self._df = float(df)
        self._scale = scale
        self._p = square_dim(scale)
        self._scale = self._scale.reshape(self._p, self._p)
        if rng is None:
            self._rng = onp.random.RandomState()
        else:
            if type(rng).__name__ == 'RandomState':
                self._rng = rng
            else:
                raise TypeError
        pass

    def set_rng(self, rng):
        assert type(rng).__name__ == 'Generator'
        self._rng = rng
        pass

    def log_prob(self, x):
        return scipy.stats.invwishart.logpdf(x=x, df=self._df, scale=self._scale)

    def sample(self, num_samples=1):
        return scipy.stats.invwishart.rvs(size=num_samples, df=self._df, scale=self._scale, random_state=self._rng)

class gaussian_distr(object):
    def __init__(self, mean, cov, rng=None):
        self._p = square_dim(cov)
        self._mean = onp.array(mean).reshape(self._p, -1)
        self._cov = onp.array(cov).reshape(self._p, self._p)
        if rng is None:
            self._rng = onp.random.default_rng()
        else:
            assert type(rng).__name__ == 'Generator'
            self._rng = rng
        pass

    def set_rng(self, rng):
        assert type(rng).__name__ == 'Generator'
        self._rng = rng
        pass

    def log_prob(self, x):
        x = onp.array(x).reshape(self._p, -1)
        return array_to_float(-self._p/2. *onp.log(2*onp.pi) - 0.5*logdet(self._cov) - 0.5*diag((x-self._mean).T @ inv(self._cov) @ (x-self._mean)))

    def sample(self, num_samples=1):
        return self._rng.multivariate_normal(size=num_samples, mean=self._mean.flatten(), cov=self._cov)


class t_distr(object):
    def __init__(self, df, mean, scale, rng=None):
        self._p = square_dim(scale)
        self._df = float(df)
        self._mean = onp.array(mean).reshape(self._p, -1)
        self._scale = onp.array(scale).reshape(self._p, self._p)
        if rng is None:
            self._rng = onp.random.default_rng()
        else:
            assert type(rng).__name__ == 'Generator'
            self._rng = rng
        pass

    def set_rng(self, rng):
        assert type(rng).__name__ == 'Generator'
        self._rng = rng
        pass

    def log_prob(self, x):
        x = onp.array(x).reshape(self._p, -1)
        return array_to_float(scipy.special.loggamma((self._df + self._p)/2.) - scipy.special.loggamma(self._df/2.) - 0.5*(self._p*(onp.log(self._df) + onp.log(onp.pi)) + logdet(self._scale)) - (self._df + self._p)/2. * onp.log(1. + 1./self._df * diag((x - self._mean).T @ onp.linalg.inv(self._scale) @ (x - self._mean))))

    def sample(self, num_samples=1, return_aux=False, aux=None):
        gaussian = self._rng.multivariate_normal(size=num_samples, mean=onp.zeros(self._p), cov=self._scale)
        if aux is None:
            aux = self._rng.chisquare(size=num_samples, df=self._df)/self._v
        else:
            assert len(aux.flatten()) == num_samples

        samples = self._mean.T + gaussian/onp.sqrt(aux.reshape(num_samples, 1))
        if return_aux == False:
            return samples
        else:
            return samples, aux

class chisquare_distr(object):
    def __init__(self, df, rng=None):
        self._df = df
        if rng is None:
            self._rng = onp.random.default_rng()
        else:
            assert type(rng).__name__ == 'Generator'
            self._rng = rng
        pass

    def set_rng(self, rng):
        assert type(rng).__name__ == 'Generator'
        self._rng = rng
        pass
    
    def log_prob(self,x):
        return -(self._df/2. * onp.log(2) + scipy.special.loggamma(self._df/2.)) + (self._df/2.-1.)*onp.log(x) - x/2.
    
    def sample(self, num_samples=1):
        return self._rng.chisquare(size=num_samples, df=self._df)

class dirichlet_distr(object):
    def __init__(self, alpha, rng=None):
        self._alpha = onp.array(alpha)
        self._k = self._alpha.shape[0]
        assert self._k >= 2
        self._alpha = self._alpha.reshape(self._k, -1)
        if rng is None:
            self._rng = onp.random.default_rng()
        else:
            assert type(rng).__name__ == 'Generator'
            self._rng = rng
        pass

    def set_rng(self, rng):
        assert type(rng).__name__ == 'Generator'
        self._rng = rng
        pass

    def log_prob(self, x):
        x = onp.array(x).reshape(self._k, -1)
        return array_to_float(((self._alpha-1) * onp.log(x)).sum(axis=0) - scipy.special.loggamma(self._alpha).sum() + scipy.special.loggamma(self._alpha.sum()))

    def sample(self, num_samples=1):
        return self._rng.dirichlet(size=num_samples, alpha=self._alpha.flatten())

class categorical_distr(object):
    def __init__(self, pi, rng=None):
        self._pi = onp.array(pi).flatten()
        self._a = self._pi.shape[0]
        if rng is None:
            self._rng = onp.random.default_rng()
        else:
            assert type(rng).__name__ == 'Generator'
            self._rng = rng
        pass

    def set_rng(self, rng):
        assert type(rng).__name__ == 'Generator'
        self._rng = rng
        pass

    def log_prob(self, x):
        return (onp.log(self._pi[x]).sum(axis=0))

    def sample(self, num_samples=1):
        return self._rng.choice(size=num_samples, a=self._a, p=self._pi)

#######################################################################
############################## Samplers ###############################
#######################################################################
'''
Generic sampler class
'''
class model_sampler(object):
    def __init__(self, **kwargs):
        self._nproc = 1
        for key, value in kwargs.items():
            setattr(self, '_' + key, value)
        if hasattr(self, '_seed'):
            self._seed_sequence = onp.random.SeedSequence(self._seed)
        else:
            self._seed_sequence = onp.random.SeedSequence()
        self.set_nproc(self._nproc)
        pass
        
    @property
    def sample_dim(self):
        pass

    @property
    def theta_indices(self):
        pass

    def drawPrior(self):
        pass

    def drawLikelihood(self):
        pass

    def drawPosterior(self):
        pass
    
    ## Forward, backward, successive sampling
    def forward(self, num_samples, rng):
        samples = onp.empty([num_samples, self.sample_dim])
        for i in range(num_samples):
            sample_prior = self.drawPrior(rng)
            sample_likelihood = self.drawLikelihood(rng)
            samples[i, :] = onp.hstack([sample_likelihood, sample_prior])
        return samples

    def backward(self, num_samples, burn_in_samples, rng):
        samples = onp.empty([num_samples, self.sample_dim])
        for i in range(int(num_samples)):
            self.drawPrior(rng)
            sample_likelihood = self.drawLikelihood(rng)
            for _ in range(int(burn_in_samples+1)):           
                sample_posterior = self.drawPosterior(rng)
            samples[i, :] = onp.hstack([sample_likelihood, sample_posterior])
        return samples

    def successive(self, num_samples, rng):
        samples = onp.empty([int(num_samples), self.sample_dim])
        self.drawPrior(rng)
        for i in range(int(num_samples)):
            sample_likelihood = self.drawLikelihood(rng)
            sample_posterior = self.drawPosterior(rng)
            samples[i, :] = onp.hstack([sample_likelihood, sample_posterior])
        return samples

    # Generate `num_chains` chains of `num_samples` successive samples
    def chains_successive(self, num_samples, num_chains, rng):
        if num_chains == 1:
            return self.successive(num_samples, rng)
        elif num_chains > 1:
            lst_out = [None] * num_chains
            for i in range(num_chains):
                lst_out[i] = self.successive(num_samples, rng)
            return lst_out

    ## Functions for random number generation and multithreading
    def set_seed(self, seed=None):
        if seed is None:
            self._seed_sequence = onp.random.SeedSequence()
        else:
            self._seed = seed
            self._seed_sequence = onp.random.SeedSequence(seed)
        self.init_rng()
        pass

    def set_nproc(self, nproc):
        self._nproc = nproc
        self.init_rng()
        pass
    
    def init_rng(self):
        child_seed_seq = self._seed_sequence.spawn(self._nproc + 1)
        # multi-threaded
        child_seed_seq_m = child_seed_seq[:-1]
        self._bitgen_m = [onp.random.MT19937(s) for s in child_seed_seq_m]
        self._rng_m = [onp.random.Generator(bg) for bg in self._bitgen_m]
        # single-threaded
        child_seed_seq_s = child_seed_seq[-1]
        self._bitgen_s = onp.random.MT19937(child_seed_seq_s)
        self._rng_s = onp.random.Generator(self._bitgen_s)        
        pass
    
    def jump_rng(self, type_rng):
        if type_rng == 'm':
            self._bitgen_m = [bg.jumped() for bg in self._bitgen_m]
            self._rng_m = [onp.random.Generator(bg) for bg in self._bitgen_m]
        elif type_rng == 's':
            self._bitgen_s = self._bitgen_s.jumped()
            self._rng_s = onp.random.Generator(self._bitgen_s)
        else:
            raise ValueError
        pass
    
    # Marginal-conditional sampler
    def sample_mc(self, num_samples):
        if self._nproc == 1:
            samples = self.forward(int(num_samples), self._rng_s)
        else:
            lst_num_samples = splitIter(int(num_samples), self._nproc)
            pool = multiprocessing.Pool(processes=self._nproc)
            out = pool.starmap(self.forward, zip(lst_num_samples, self._rng_m))
            pool.close()
            samples = onp.vstack(out)
            self.jump_rng('m')
        return samples

    # Successive-conditional sampler
    def sample_sc(self, num_samples, num_chains=1):
        if num_chains == 1:
            samples = self.successive(int(num_samples), self._rng_s)
        elif num_chains > 1:
            lst_chains = splitIter(int(num_chains), self._nproc)
            pool = multiprocessing.Pool(processes=self._nproc)
            out = pool.starmap(self.chains_successive, zip(repeat(num_samples), lst_chains, self._rng_m))
            pool.close()
            samples = reduce(lambda x, y: x + y, out)
            self.jump_rng('m')
        else:
            raise ValueError
        return samples

    # Backward-conditional sampler
    def sample_bc(self, num_samples, burn_in_samples):
        if self._nproc == 1:
            samples = self.backward(int(num_samples), int(burn_in_samples), self._rng_s)
        else:    
            lst_num_samples = splitIter(int(num_samples), self._nproc)
            pool = multiprocessing.Pool(processes=self._nproc)
            out = pool.starmap(self.backward, zip(lst_num_samples, repeat(burn_in_samples), self._rng_m))
            pool.close()
            samples = onp.vstack(out)
            self.jump_rng('m')
        return samples

    # 
    def test_functions(self, samples):
        return geweke_functions(samples)


# ''' 
# Mixture of d-dimensional t-distributions
# Parameters:
#     D: dimension of each t-distribution
#     v: degrees of freedom of each t-distribution
#     M: mixture number
#     N: observation number
#     m_mu, S_mu: hyperparameters (mean and variance) for Gaussian prior on mu. Must be provided as lists
#     v_Sigma, Psi_Sigma: hyperparameters for Inverse Wishart prior on Sigma. When D=1, reduces to Inverse Gamma with alpha=v/2 and beta=Psi/2
#     alpha_p: hyperparameters for Dirichlet prior on p.
# '''
# class t_mixture_sampler(model_sampler):
#     def __init__(self, **kwargs):
#         super().__init__(**kwargs)

#         # Check inputs
#         for attr in ['_D', '_M', '_N', '_v', '_m_mu', '_S_mu', '_v_Sigma', '_Psi_Sigma', '_alpha_p']:
#             assert hasattr(self, attr)

#         self._D = int(self._D)
#         self._M = int(self._M)
#         self._N = int(self._N)
#         self._alpha_p = onp.array(self._alpha_p).flatten()

#         assert len(self._m_mu) == len(self._S_mu)
#         assert len(self._S_mu) == len(self._v_Sigma)
#         assert len(self._v_Sigma) == len(self._Psi_Sigma)
#         assert len(self._Psi_Sigma) == self._M

#         assert onp.vstack(self._m_mu).shape == (self._D*self._M, 1)

#         for k in range(self._M):
#             assert square_dim(self._S_mu[k]) == self._D
#             assert square_dim(self._v_Sigma[k]) == 1
#             assert square_dim(self._Psi_Sigma[k]) == self._D

#         assert self._alpha_p.shape == (self._M,)
#         pass

#     @property
#     def sample_dim(self):
#         # (y) + (Sigma, mu, p) + (s, w)
#         return self._D*self._N + (self._D ** 2 + self._D + 1)*self._M - 1 + 2*self._N

#     @property
#     def theta_indices(self):
#         return onp.arange(self._N * self._D, self._N + (self._D ** 2 + self._D + 1)*self._M - 1)

#     def drawPrior(self, rng=None):
#         if rng is None:
#             rng = onp.random.Generator(onp.random.MT19937())

#         # Set random state for invwishart sampling
#         rng_randState = onp.random.RandomState()
#         rng_randState.set_state(rng.bit_generator.state)

#         if not hasattr(self, '_p_distr_prior'):
#             self._mu_distr_prior = [gaussian_distr(
#                 mean=self._m_mu[k], cov=self._S_mu[k], rng=rng) for k in range(self._M)]
#             self._Sigma_distr_prior = [invwishart_distr(
#                 df=self._v_Sigma[k], scale=self._Psi_Sigma[k], rng=rng_randState) for k in range(self._M)]
#             self._p_distr_prior = dirichlet_distr(alpha=self._alpha_p, rng=rng)

#         self._mu = [self._mu_distr_prior[k].sample()
#                     for k in range(int(self._M))]
#         self._Sigma = [self._Sigma_distr_prior[k].sample()
#                        for k in range(int(self._M))]
#         self._p = self._p_distr_prior.sample().flatten()

#         # draw latent variable s, auxiliary variable w
#         s_distr = categorical_distr(pi=self._p.flatten(), rng=rng)
#         self._s = s_distr.sample(num_samples=self._N).flatten()
#         if not hasattr(self, '_chisquare_distr'):
#             self._chisquare_distr = chisquare_distr(df=self._v, rng=rng)
#         self._w = self._chisquare_distr.sample(num_samples=self._N).flatten()/self._v

#         return onp.hstack([onp.array(self._mu).reshape(1, -1).flatten(), onp.array(self._Sigma).reshape(1, -1).flatten(), self._p[:-1], self._s, self._w])

#     def drawLikelihood(self, rng=None):
#         if rng is None:
#             rng = onp.random.Generator(onp.random.MT19937())
#         if not hasattr(self, '_y'):
#             self._y = onp.empty([self._N, self._D])

#         y_distr = [t_distr(df=self._v, mean=self._mu[k].flatten(), scale=self._Sigma[k], rng=rng) for k in range(self._M)]
#         for i in range(self._N):
#             self._y[i, :] = y_distr[self._s[i]].sample(aux=self._w[i]).flatten()

#         return self._y.reshape(1, -1).flatten()

#     def drawPosterior(self, rng=None):
#         if rng is None:
#             rng = onp.random.Generator(onp.random.MT19937())

#         # Set random state for invwishart sampling
#         rng_randState = onp.random.RandomState()
#         rng_randState.set_state(rng.bit_generator.state)

#         self.drawPosterior_s(rng)
#         self.drawPosterior_Sigma(rng_randState)
#         self.drawPosterior_mu(rng)
#         self.drawPosterior_p(rng)

#         return onp.hstack([onp.array(self._mu).reshape(1, -1).flatten(), onp.array(self._Sigma).reshape(1, -1).flatten(), self._p[:-1], self._s, self._w])

#     def drawPosterior_s(self, rng):
#         s_distr_cond = self.getCond_s(rng)
#         proposal = self._s.copy()
#         for i in range(self._N):
#             proposal[i] = s_distr_cond[i].sample()
#         self._s = proposal
#         return proposal, s_distr_cond

#     def drawPosterior_w(self, rng):
#         proposal = self._w.copy()
#         chisq_coeff = (self._v + onp.array([XTWX((self._y[i, :]-self._mu[self._s[i]]).reshape(
#             -1, 1), inv(self._Sigma[self._s[i]], return_array=True)) for i in range(self._N)])).flatten()
#         chisq_distr_cond = self.getCond_chisq(rng)
#         proposal = chisq_distr_cond.sample(num_samples=self._N).flatten()/chisq_coeff
#         self._w = proposal
#         return proposal, chisq_coeff, chisq_distr_cond

#     def drawPosterior_Sigma(self, rng):
#         Sigma_distr_cond = self.getCond_Sigma(rng)
#         proposal = self._Sigma.copy()
#         for k in range(self._M):
#             proposal[k] = Sigma_distr_cond[k].sample()
#         self._Sigma = proposal
#         return proposal, Sigma_distr_cond

#     def drawPosterior_mu(self, rng):
#         mu_distr_cond = self.getCond_mu(rng)
#         proposal = self._mu.copy()
#         for k in range(self._M):
#             proposal[k] = mu_distr_cond[k].sample()
#         self._mu = proposal
#         return proposal, mu_distr_cond

#     def drawPosterior_p(self, rng):
#         p_distr_cond = self.getCond_p(rng)
#         proposal = p_distr_cond.sample().flatten()
#         self._p = proposal
#         return proposal, p_distr_cond

#     def getCond_mu(self, rng):
#         mu_distr_cond = [None] * self._M
#         for k in range(self._M):
#             s_k = (self._s == k)
#             num_s_k = s_k.sum()
#             if num_s_k == 0:
#                 mu_pr, Sigma_pr = self._m_mu[k], self._S_mu[k]
#             else:
#                 lst_mu_k = onp.vsplit(
#                     self._y[s_k, :].reshape(num_s_k, self._D), num_s_k)
#                 lst_Sigma_k = self._Sigma[k]/self._w[s_k]
#                 mu_pr, Sigma_pr = GaussianProductMV(
#                     mu_0=self._m_mu[k], Sigma_0=self._S_mu[k], lst_mu=lst_mu_k, lst_Sigma=lst_Sigma_k)
#             mu_distr_cond[k] = gaussian_distr(
#                 mean=mu_pr, cov=Sigma_pr, rng=rng)
#         return mu_distr_cond

#     def getCond_Sigma(self, rng):
#         Sigma_distr_cond = [None] * self._M
#         for k in range(self._M):
#             s_k = (self._s == k)
#             num_s_k = s_k.sum()
#             Sigma_distr_cond[k] = invwishart_distr(df=self._v_Sigma[k] + num_s_k,
#                                                    scale=self._Psi_Sigma[k] + XTWX(self._y[s_k, :].reshape(
#                                                        num_s_k, self._D)-self._mu[k].reshape(1, self._D), diagMatrix(self._w[s_k])),
#                                                    rng=rng)
#         return Sigma_distr_cond

#     def getCond_s(self, rng):
#         y_distr = [t_distr(df=self._v, mean=self._mu[k].flatten(
#         ), scale=self._Sigma[k], rng=rng) for k in range(self._M)]
#         s_distr_cond = [None] * self._N
#         log_res = onp.vstack([y_distr[k].log_prob(x=self._y.T)
#                              for k in range(self._M)])
#         log_res = onp.log(self._p.reshape(-1, 1)) + log_res
#         res = onp.exp(log_res)
#         res = res/(res.sum(0).reshape(1, -1))
#         for i in range(self._N):
#             s_distr_cond[i] = categorical_distr(pi=res[:, i], rng=rng)
#         return s_distr_cond

#     def getCond_p(self, rng):
#         counts = onp.bincount(self._s, minlength=int(self._M))
#         p_distr_cond = dirichlet_distr(alpha=self._alpha_p.flatten() + counts)
#         return p_distr_cond
    
#     def getCond_chisq(self, rng):
#         chisq_distr_cond = chisquare_distr(df=self._v+self._D)
#         return chisq_distr_cond

#     # Testing
#     def joint_log_prob(self, mu=None, Sigma=None, p=None, s=None, w=None, y=None):
#         if mu is None:
#             mu = self._mu
#         if Sigma is None:
#             Sigma = self._Sigma
#         if p is None:
#             p = self._p
#         if s is None:
#             s = self._s
#         if w is None:
#             w = self._w
#         if y is None:
#             y = self._y
#         s = s.astype('int')
#         s_distr = categorical_distr(pi=p.flatten())
#         y_distr = [gaussian_distr(mean=mu[s[i]].flatten(), cov=Sigma[s[i]]/w[i])
#                    for i in range(self._N)]
#         prior_log_prob = onp.array([self._mu_distr_prior[k].log_prob(mu[k]) + self._Sigma_distr_prior[k].log_prob(
#             Sigma[k]) for k in range(self._M)]).sum() + self._p_distr_prior.log_prob(p) + s_distr.log_prob(s) + self._chisquare_distr.log_prob(self._v*w).sum()
#         likelihood_log_prob = onp.array(
#             [y_distr[i].log_prob(y[i, :].T) for i in range(self._N)]).sum()
#         return prior_log_prob + likelihood_log_prob

#     def testCond_mu(self):
#         self.drawPrior()
#         self.drawLikelihood()
#         mu_tm1 = self._mu.copy()
#         mu_t, mu_distr_cond = self.drawPosterior_mu(onp.random.default_rng())
#         diff_cond_log_prob = onp.array([mu_distr_cond[k].log_prob(
#             mu_t[k]) - mu_distr_cond[k].log_prob(mu_tm1[k]) for k in range(self._M)]).sum()
#         diff_joint_log_prob = self.joint_log_prob(
#             mu=mu_t) - self.joint_log_prob(mu=mu_tm1)
#         assert onp.allclose(diff_cond_log_prob, diff_joint_log_prob)
#         return True

#     def testCond_Sigma(self):
#         self.drawPrior()
#         self.drawLikelihood()
#         Sigma_tm1 = self._Sigma.copy()
#         Sigma_t, Sigma_distr_cond = self.drawPosterior_Sigma(
#             onp.random.RandomState())
#         diff_cond_log_prob = onp.array([Sigma_distr_cond[k].log_prob(
#             Sigma_t[k]) - Sigma_distr_cond[k].log_prob(Sigma_tm1[k]) for k in range(self._M)]).sum()
#         diff_joint_log_prob = self.joint_log_prob(
#             Sigma=Sigma_t) - self.joint_log_prob(Sigma=Sigma_tm1)
#         assert onp.allclose(diff_cond_log_prob, diff_joint_log_prob)
#         return True

#     def testCond_s(self):
#         self.drawPrior()
#         self.drawLikelihood()
#         s_tm1 = self._s.copy()
#         s_t, s_distr_cond = self.drawPosterior_s(onp.random.default_rng())
#         diff_cond_log_prob = onp.array([s_distr_cond[i].log_prob(
#             s_t[i]) - s_distr_cond[i].log_prob(s_tm1[i]) for i in range(self._N)]).sum()
#         diff_joint_log_prob = self.joint_log_prob(s=s_t) - self.joint_log_prob(s=s_tm1)
#         assert onp.allclose(diff_cond_log_prob, diff_joint_log_prob)
#         return True

#     def testCond_w(self):
#         self.drawPrior()
#         self.drawLikelihood()
#         w_tm1 = self._w.copy()
#         w_t, chisq_coeff, chisq_distr_cond = self.drawPosterior_w(onp.random.default_rng())
#         diff_cond_log_w = chisq_distr_cond.log_prob(chisq_coeff*w_t).sum() - chisq_distr_cond.log_prob(chisq_coeff*w_tm1).sum()
#         diff_joint_log_w = self.joint_log_prob(w=w_t) - self.joint_log_prob(w=w_tm1)
#         assert onp.allclose(diff_cond_log_w, diff_joint_log_w)
#         return True

#     def testCond_p(self):
#         self.drawPrior()
#         self.drawLikelihood()
#         p_tm1 = self._p.copy()
#         p_t, p_distr_cond = self.drawPosterior_p(onp.random.default_rng())
#         diff_cond_log_prob = p_distr_cond.log_prob(p_t) - p_distr_cond.log_prob(p_tm1)
#         diff_joint_log_prob = self.joint_log_prob(p=p_t) - self.joint_log_prob(p=p_tm1)
#         assert onp.allclose(diff_cond_log_prob, diff_joint_log_prob)
#         return True

#     def testCond(self):
#         self.testCond_mu()
#         self.testCond_Sigma()
#         self.testCond_p()
#         self.testCond_s()
#         self.testCond_w()
#         return True

# '''
# Geweke Errors

# 1. The prior distribution of p is beta(1, 1), whereas the posterior simulator assumes a beta(2, 2) prior distribution.
# 2. In the successive-conditional simulator, the observables simulator ignores w_t from the posterior simulator. Instead, it uses fresh values of w_t ~ chi^2(v)/v to construct y_t
# 3. The degrees of freedom in the conditional posterior distribution of each w_t is taken to be 5, rather than its correct value of 6.
# 4. The variance of the Gaussian conditional posterior distribution of mu is erroneously set to 0.
# 5. The correct algorithm generates s_t (conditional on all unknowns except w_t) and then generates w_t conditional on
# all unknowns including s_t just drawn. In the error, w_t is drawn several steps later in the Gibbs sampling algorithm
# rather than immediately after s_t.
# '''

# ''' 
# Mixture of d-dimensional Gaussians
# Parameters:
#     D: dimension of each Gaussian
#     M: mixture number
#     N: observation number
#     m_mu, S_mu: hyperparameters (mean and variance) for Gaussian prior on mu. Must be provided as lists
#     v_Sigma, Psi_Sigma: hyperparameters for Inverse Wishart prior on Sigma. When D=1, reduces to Inverse Gamma with alpha=v/2 and beta=Psi/2
#     alpha_p: hyperparameters for Dirichlet prior on p.
# '''
# class gaussian_mixture_sampler(model_sampler):
#     def __init__(self, **kwargs):
#         super().__init__(**kwargs)

#         # Check inputs
#         for attr in ['_D', '_M', '_N', '_m_mu', '_S_mu', '_v_Sigma', '_Psi_Sigma', '_alpha_p']:
#             assert hasattr(self, attr)

#         self._D = int(self._D)
#         self._M = int(self._M)
#         self._N = int(self._N)
#         self._alpha_p = onp.array(self._alpha_p).reshape(self._M, 1)

#         assert len(self._m_mu) == len(self._S_mu)
#         assert len(self._S_mu) == len(self._v_Sigma)
#         assert len(self._v_Sigma) == len(self._Psi_Sigma)
#         assert len(self._Psi_Sigma) == self._M

#         assert onp.vstack(self._m_mu).shape == (self._D*self._M, 1)

#         for k in range(self._M):
#             assert square_dim(self._S_mu[k]) == self._D
#             assert square_dim(self._v_Sigma[k]) == 1
#             assert square_dim(self._Psi_Sigma[k]) == self._D
#         pass

#     @property
#     def sample_dim(self):
#         # (y) + (Sigma, mu, p) + (s)
#         return self._D*self._N + (self._D ** 2 + self._D + 1)*self._M - 1 + self._N

#     @property
#     def theta_indices(self):
#         return onp.arange(self._N * self._D, self._N * self._D + (self._D ** 2 + self._D + 1)*self._M - 1)

#     def drawPrior(self, rng=None):
#         if rng is None:
#             rng = onp.random.Generator(onp.random.MT19937())
        
#         # Set random state for invwishart sampling
#         rng_randState = onp.random.RandomState()
#         rng_randState.set_state(rng.bit_generator.state)

#         if not hasattr(self, '_p_distr_prior'):
#             self._mu_distr_prior = [gaussian_distr(mean=self._m_mu[k], cov=self._S_mu[k], rng=rng) for k in range(self._M)]
#             self._Sigma_distr_prior = [invwishart_distr(df=self._v_Sigma[k], scale=self._Psi_Sigma[k], rng=rng_randState) for k in range(self._M)]
#             self._p_distr_prior = dirichlet_distr(alpha=self._alpha_p, rng=rng)

#         self._mu = [self._mu_distr_prior[k].sample() for k in range(int(self._M))]
#         self._Sigma = [self._Sigma_distr_prior[k].sample() for k in range(int(self._M))]
#         self._p = self._p_distr_prior.sample().flatten()

#         # draw latent variable s
#         s_distr = categorical_distr(pi=self._p.flatten())
#         self._s = s_distr.sample(num_samples=self._N).flatten()
#         return onp.hstack([onp.array(self._mu).reshape(1,-1).flatten(), onp.array(self._Sigma).reshape(1,-1).flatten(), self._p[:-1], self._s])

#     def drawLikelihood(self, rng=None):
#         if rng is None:
#             rng = onp.random.Generator(onp.random.MT19937())
#         if not hasattr(self, '_y'):
#             self._y = onp.empty([self._N, self._D])
        
#         y_distr = [gaussian_distr(mean=self._mu[k].flatten(), cov=self._Sigma[k], rng=rng) for k in range(self._M)]
#         for i in range(self._N):
#             self._y[i, :] = y_distr[self._s[i]].sample().flatten()

#         return self._y.reshape(1,-1).flatten()

#     def drawPosterior(self, rng=None):
#         if rng is None:
#             rng = onp.random.Generator(onp.random.MT19937())
        
#         # Set random state for invwishart sampling
#         rng_randState = onp.random.RandomState()
#         rng_randState.set_state(rng.bit_generator.state)
        
#         self.drawPosterior_s(rng)
#         self.drawPosterior_Sigma(rng_randState)
#         self.drawPosterior_mu(rng)
#         self.drawPosterior_p(rng)
        
#         return onp.hstack([onp.array(self._mu).reshape(1,-1).flatten(), onp.array(self._Sigma).reshape(1,-1).flatten(), self._p[:-1], self._s])
        
#     def drawPosterior_s(self, rng):
#         s_distr_cond = self.getCond_s(rng)
#         proposal = self._s.copy()
#         for i in range(self._N):
#             proposal[i] = s_distr_cond[i].sample()
#         self._s = proposal
#         return proposal, s_distr_cond
        
        
#     def drawPosterior_Sigma(self, rng):
#         Sigma_distr_cond = self.getCond_Sigma(rng)
#         proposal = self._Sigma.copy()
#         for k in range(self._M):
#             proposal[k] = Sigma_distr_cond[k].sample()
#         self._Sigma = proposal
#         return proposal, Sigma_distr_cond
        
#     def drawPosterior_mu(self, rng):
#         mu_distr_cond = self.getCond_mu(rng)
#         proposal = self._mu.copy()
#         for k in range(self._M):
#             proposal[k] = mu_distr_cond[k].sample()
#         self._mu = proposal  
#         return proposal, mu_distr_cond
        
#     def drawPosterior_p(self, rng):
#         p_distr_cond = self.getCond_p(rng)
#         proposal = p_distr_cond.sample().flatten()
#         self._p = proposal
#         return proposal, p_distr_cond

#     def getCond_mu(self, rng):
#         mu_distr_cond = [None] * self._M
#         for k in range(self._M):
#             s_k = (self._s == k)
#             num_s_k = s_k.sum()
#             if num_s_k == 0:
#                 m_mu_k_cond, S_mu_k_cond = self._m_mu[k], self._S_mu[k]
#             else:
#                 S_mu_k_inv = inv(self._S_mu[k])
#                 Sigma_k_inv = inv(self._Sigma[k])
#                 S_mu_k_cond = inv(S_mu_k_inv + num_s_k*Sigma_k_inv)
#                 m_mu_k_cond = S_mu_k_cond @ (S_mu_k_inv @ self._m_mu[k] + Sigma_k_inv @ self._y[s_k, :].reshape(num_s_k, self._D).sum(0).reshape(self._D, 1))

#             mu_distr_cond[k] = gaussian_distr(
#                 mean=m_mu_k_cond, cov=S_mu_k_cond, rng=rng)
#         return mu_distr_cond

#     def getCond_Sigma(self, rng):
#         Sigma_distr_cond = [None] * self._M
#         for k in range(self._M):
#             s_k = (self._s == k)
#             num_s_k = s_k.sum()
#             Sigma_distr_cond[k] = invwishart_distr(df=self._v_Sigma[k] + num_s_k, 
#                                         scale=self._Psi_Sigma[k] + XTX(self._y[s_k, :].reshape(num_s_k, self._D)-self._mu[k].reshape(1, self._D)), 
#                                         rng=rng)         
#         return Sigma_distr_cond

#     def getCond_s(self, rng):
#         y_distr = [gaussian_distr(mean=self._mu[k].flatten(), cov=self._Sigma[k], rng=rng) for k in range(self._M)]
#         s_distr_cond = [None] * self._N
#         log_res = onp.vstack([y_distr[k].log_prob(x=self._y.T) for k in range(self._M)])
#         log_res = onp.log(self._p.reshape(-1,1)) + log_res
#         res = onp.exp(log_res)
#         res = res/(res.sum(0).reshape(1, -1))
#         for i in range(self._N):
#             s_distr_cond[i] = categorical_distr(pi=res[:, i], rng=rng)
#         return s_distr_cond
    
#     def getCond_p(self, rng):
#         counts = onp.bincount(self._s, minlength = int(self._M))
#         p_distr_cond = dirichlet_distr(alpha=self._alpha_p.flatten() + counts)
#         return p_distr_cond
    
#     # Testing
#     def joint_log_prob(self, mu=None, Sigma=None, p=None, s=None, y=None):
#         if mu is None:
#             mu = self._mu
#         if Sigma is None:
#             Sigma = self._Sigma
#         if p is None:
#             p = self._p
#         if s is None:
#             s = self._s
#         if y is None:
#             y = self._y
#         s_distr = categorical_distr(pi=p.flatten())
#         y_distr = [gaussian_distr(mean=mu[k].flatten(), cov=Sigma[k]) for k in range(self._M)]
#         prior_log_prob = onp.array([self._mu_distr_prior[k].log_prob(mu[k]) + self._Sigma_distr_prior[k].log_prob(Sigma[k]) for k in range(self._M)]).sum() + self._p_distr_prior.log_prob(p) + s_distr.log_prob(s)
#         likelihood_log_prob = onp.array([y_distr[s[i]].log_prob(y[i, :].T) for i in range(self._N)]).sum()
#         return prior_log_prob + likelihood_log_prob
    
#     def testCond_mu(self):
#         self.drawPrior()
#         self.drawLikelihood()
#         mu_tm1 = self._mu.copy()
#         mu_t, mu_distr_cond = self.drawPosterior_mu(onp.random.default_rng())
#         diff_cond_log_prob = onp.array([mu_distr_cond[k].log_prob(mu_t[k]) - mu_distr_cond[k].log_prob(mu_tm1[k]) for k in range(self._M)]).sum()
#         diff_joint_log_prob = self.joint_log_prob(mu=mu_t) - self.joint_log_prob(mu=mu_tm1)
#         assert onp.allclose(diff_cond_log_prob, diff_joint_log_prob)
#         return True
        
#     def testCond_Sigma(self):
#         self.drawPrior()
#         self.drawLikelihood()
#         Sigma_tm1 = self._Sigma.copy()
#         Sigma_t, Sigma_distr_cond = self.drawPosterior_Sigma(onp.random.RandomState())
#         diff_cond_log_prob = onp.array([Sigma_distr_cond[k].log_prob(Sigma_t[k]) - Sigma_distr_cond[k].log_prob(Sigma_tm1[k]) for k in range(self._M)]).sum()
#         diff_joint_log_prob = self.joint_log_prob(Sigma=Sigma_t) - self.joint_log_prob(Sigma=Sigma_tm1)
#         assert onp.allclose(diff_cond_log_prob, diff_joint_log_prob)
#         return True
    
#     def testCond_s(self):
#         self.drawPrior()
#         self.drawLikelihood()
#         s_tm1 = self._s.copy()
#         s_t, s_distr_cond = self.drawPosterior_s(onp.random.default_rng())
#         diff_cond_log_prob = onp.array([s_distr_cond[i].log_prob(s_t[i]) - s_distr_cond[i].log_prob(s_tm1[i]) for i in range(self._N)]).sum()
#         diff_joint_log_prob = self.joint_log_prob(s=s_t) - self.joint_log_prob(s=s_tm1)
#         assert onp.allclose(diff_cond_log_prob, diff_joint_log_prob)
#         return True
        
#     def testCond_p(self):
#         self.drawPrior()
#         self.drawLikelihood()
#         p_tm1 = self._p.copy()
#         p_t, p_distr_cond = self.drawPosterior_p(onp.random.default_rng())
#         diff_cond_log_prob = p_distr_cond.log_prob(p_t) - p_distr_cond.log_prob(p_tm1)
#         diff_joint_log_prob = self.joint_log_prob(p=p_t) - self.joint_log_prob(p=p_tm1)
#         assert onp.allclose(diff_cond_log_prob, diff_joint_log_prob)
#         return True

#     def testCond(self):
#         self.testCond_mu()
#         self.testCond_Sigma()
#         self.testCond_p()
#         self.testCond_s()
#         return True

''' 
Mixture of d-dimensional Gaussians. Gibbs posterior sampler collapses p for faster mixing.
Parameters:
    D: dimension of each Gaussian
    M: mixture number
    N: observation number
    m_mu, S_mu: hyperparameters (mean and variance) for Gaussian prior on mu. Must be provided as lists
    v_Sigma, Psi_Sigma: hyperparameters for Inverse Wishart prior on Sigma. When D=1, reduces to Inverse Gamma with alpha=v/2 and beta=Psi/2
    alpha_p: hyperparameters for Dirichlet prior on p.
'''
class gaussian_mixture_sampler(model_sampler):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Check inputs
        for attr in ['_D', '_M', '_N', '_m_mu', '_S_mu', '_v_Sigma', '_Psi_Sigma', '_alpha_p']:
            assert hasattr(self, attr)

        self._D = int(self._D)
        self._M = int(self._M)
        self._N = int(self._N)
        self._alpha_p = onp.array(self._alpha_p).reshape(self._M, 1)

        assert len(self._m_mu) == len(self._S_mu)
        assert len(self._S_mu) == len(self._v_Sigma)
        assert len(self._v_Sigma) == len(self._Psi_Sigma)
        assert len(self._Psi_Sigma) == self._M

        assert onp.vstack(self._m_mu).shape == (self._D*self._M, 1)

        for k in range(self._M):
            assert square_dim(self._S_mu[k]) == self._D
            assert square_dim(self._v_Sigma[k]) == 1
            assert square_dim(self._Psi_Sigma[k]) == self._D
        pass

    @property
    def sample_dim(self):
        # (y) + (Sigma, mu) + (s)
        return self._D*self._N + (self._D ** 2 + self._D)*self._M + self._N

    @property
    def theta_indices(self):
        return onp.arange(self._N * self._D, self._N * self._D + (self._D ** 2 + self._D )*self._M)

    def drawPrior(self, rng=None):
        if rng is None:
            rng = onp.random.Generator(onp.random.MT19937())
        
        # Set random state for invwishart sampling
        rng_randState = onp.random.RandomState()
        rng_randState.set_state(rng.bit_generator.state)

        if not hasattr(self, '_mu_distr_prior'):
            self._mu_distr_prior = [gaussian_distr(mean=self._m_mu[k], cov=self._S_mu[k], rng=rng) for k in range(self._M)]
            self._Sigma_distr_prior = [invwishart_distr(df=self._v_Sigma[k], scale=self._Psi_Sigma[k], rng=rng_randState) for k in range(self._M)]
            self._p_distr_prior = dirichlet_distr(alpha=self._alpha_p, rng=rng)

        self._mu = [self._mu_distr_prior[k].sample() for k in range(int(self._M))]
        self._Sigma = [self._Sigma_distr_prior[k].sample() for k in range(int(self._M))]
        p = self._p_distr_prior.sample().flatten()

        # draw latent variable s
        s_distr = categorical_distr(pi=p.flatten())
        self._s = s_distr.sample(num_samples=self._N).flatten()
        return onp.hstack([onp.array(self._mu).reshape(1,-1).flatten(), onp.array(self._Sigma).reshape(1,-1).flatten(), self._s])

    def drawLikelihood(self, rng=None):
        if rng is None:
            rng = onp.random.Generator(onp.random.MT19937())
        if not hasattr(self, '_y'):
            self._y = onp.empty([self._N, self._D])
        
        y_distr = [gaussian_distr(mean=self._mu[k].flatten(), cov=self._Sigma[k], rng=rng) for k in range(self._M)]
        for i in range(self._N):
            self._y[i, :] = y_distr[self._s[i]].sample().flatten()

        return self._y.reshape(1,-1).flatten()

    def drawPosterior(self, rng=None):
        if rng is None:
            rng = onp.random.Generator(onp.random.MT19937())
        
        # Set random state for invwishart sampling
        rng_randState = onp.random.RandomState()
        rng_randState.set_state(rng.bit_generator.state)
        
        self.drawPosterior_s(rng)
        self.drawPosterior_Sigma(rng_randState)
        self.drawPosterior_mu(rng)
        
        return onp.hstack([onp.array(self._mu).reshape(1,-1).flatten(), onp.array(self._Sigma).reshape(1,-1).flatten(), self._s])
        
    def drawPosterior_s(self, rng):
        s_distr_cond = self.getCond_s(rng)
        proposal = self._s.copy()
        for i in range(self._N):
            proposal[i] = s_distr_cond[i].sample()
        self._s = proposal
        return proposal, s_distr_cond
        
        
    def drawPosterior_Sigma(self, rng):
        Sigma_distr_cond = self.getCond_Sigma(rng)
        proposal = self._Sigma.copy()
        for k in range(self._M):
            proposal[k] = Sigma_distr_cond[k].sample()
        self._Sigma = proposal
        return proposal, Sigma_distr_cond
        
    def drawPosterior_mu(self, rng):
        mu_distr_cond = self.getCond_mu(rng)
        proposal = self._mu.copy()
        for k in range(self._M):
            proposal[k] = mu_distr_cond[k].sample()
        self._mu = proposal  
        return proposal, mu_distr_cond

    def getCond_mu(self, rng):
        mu_distr_cond = [None] * self._M
        for k in range(self._M):
            s_k = (self._s == k)
            num_s_k = s_k.sum()
            if num_s_k == 0:
                m_mu_k_cond, S_mu_k_cond = self._m_mu[k], self._S_mu[k]
            else:
                S_mu_k_inv = inv(self._S_mu[k])
                Sigma_k_inv = inv(self._Sigma[k])
                S_mu_k_cond = inv(S_mu_k_inv + num_s_k*Sigma_k_inv)
                m_mu_k_cond = S_mu_k_cond @ (S_mu_k_inv @ self._m_mu[k].reshape(self._D, 1) + Sigma_k_inv @ self._y[s_k, :].reshape(num_s_k, self._D).sum(0).reshape(self._D, 1))

            mu_distr_cond[k] = gaussian_distr(
                mean=m_mu_k_cond, cov=S_mu_k_cond, rng=rng)
        return mu_distr_cond

    def getCond_Sigma(self, rng):
        Sigma_distr_cond = [None] * self._M
        for k in range(self._M):
            s_k = (self._s == k)
            num_s_k = s_k.sum()
            Sigma_distr_cond[k] = invwishart_distr(df=self._v_Sigma[k] + num_s_k, 
                                        scale=self._Psi_Sigma[k] + XTX(self._y[s_k, :].reshape(num_s_k, self._D)-self._mu[k].reshape(1, self._D)), 
                                        rng=rng)         
        return Sigma_distr_cond

    def getCond_s(self, rng):
        s_distr_cond = [None] * self._N
        counts = onp.bincount(self._s, minlength=int(self._M))
        log_p_s_prior = onp.log(((self._alpha_p.flatten() + counts).reshape(1, -1) - onp.eye(self._M))/(self._N+self._alpha_p.sum()-1)) # M -> M

        y_distr = [gaussian_distr(mean=self._mu[k].flatten(), cov=self._Sigma[k], rng=rng) for k in range(self._M)]
        res = onp.vstack([y_distr[k].log_prob(x=self._y.T) for k in range(self._M)]) # M x N

        # Multiply by prior terms
        res += onp.hstack([log_p_s_prior[self._s[i],:].reshape(self._M, 1) for i in range(self._N)])
        res = onp.exp(res)
        res = res/(res.sum(0).reshape(1, -1))

        for i in range(self._N):
            s_distr_cond[i] = categorical_distr(pi=res[:, i] , rng=rng)
        return s_distr_cond

'''
Error 1: in the Sigma Gibbs step, use all y for each mixture component
'''
class gaussian_mixture_sampler_error_1(gaussian_mixture_sampler):
    def getCond_Sigma(self, rng):
        Sigma_distr_cond = [None] * self._M
        for k in range(self._M):
            s_k = (self._s == k)
            num_s_k = s_k.sum()
            # scale_new = self._Psi_Sigma[k] + XTX(self._y[s_k, :].reshape(num_s_k, self._D)-self._mu[k].reshape(1, self._D)) # correct
            scale_new = self._Psi_Sigma[k] + XTX(self._y-self._mu[k].reshape(1, self._D))
            Sigma_distr_cond[k] = invwishart_distr(df=self._v_Sigma[k] + num_s_k, 
                                        scale=scale_new, 
                                        rng=rng)
        return Sigma_distr_cond

'''
Error 2: in the s Gibbs step, forget to subtract current observations from the prior term 
'''
class gaussian_mixture_sampler_error_2(gaussian_mixture_sampler):
     def getCond_s(self, rng):
        s_distr_cond = [None] * self._N
        counts = onp.bincount(self._s, minlength=int(self._M))
        # log_p_s_prior = onp.log(((self._alpha_p.flatten() + counts).reshape(1, -1) - onp.eye(self._M))/(self._N+self._alpha_p.sum()-1)) # Correct
        log_p_s_prior = onp.log(((self._alpha_p.flatten() + counts).reshape(1, -1) - onp.identity(self._M) + onp.identity(self._M))/(self._N+self._alpha_p.sum()))

        y_distr = [gaussian_distr(mean=self._mu[k].flatten(), cov=self._Sigma[k], rng=rng) for k in range(self._M)]
        res = onp.vstack([y_distr[k].log_prob(x=self._y.T) for k in range(self._M)]) # M x N

        # Multiply by prior terms
        res += onp.hstack([log_p_s_prior[self._s[i],:].reshape(self._M, 1) for i in range(self._N)])
        res = onp.exp(res)
        res = res/(res.sum(0).reshape(1, -1))

        for i in range(self._N):
            s_distr_cond[i] = categorical_distr(pi=res[:, i] , rng=rng)
        return s_distr_cond

'''
Bayesian Lasso. Reversible Jump MCMC posterior sampler
Model based on (Chen, Wang, and McKeown 2011)
'''
class bayes_lasso_sampler(model_sampler):
    def __init__(self, N=1, p=3, Lambda=1, tau=1, alpha_sigma2=3, beta_sigma2=1, epsilon_update=1, epsilon_birth=1, **kwargs):
        self._N  = N
        self._p = p
        self._Lambda = Lambda
        self._tau = tau
        self._alpha_sigma2 = alpha_sigma2
        self._beta_sigma2 = beta_sigma2
        self._epsilon_update = epsilon_update
        self._epsilon_birth = epsilon_birth

        self._pmf_k = onp.exp(onp.arange(1, self._p+1) * onp.log(self._Lambda) -
                          self._Lambda - scipy.special.loggamma(1+onp.arange(1, self._p+1)))
        self._pmf_k = self._pmf_k/self._pmf_k.sum()
        
        super().__init__(**kwargs)
        if not hasattr(self, '_X'):
            self.drawData()
        
        # Check inputs
        for attr in ['_N', '_p', '_Lambda', '_tau', '_alpha_sigma2', '_beta_sigma2', '_epsilon_update', '_epsilon_birth']:
            assert hasattr(self, attr)
        self._N   = int(self._N)
        self._p = int(self._p)
        assert onp.all(onp.array([self._N  , self._p, self._Lambda, self._tau,
                                self._alpha_sigma2, self._beta_sigma2, self._epsilon_update, self._epsilon_birth]) > 0)
        
        self._D = 1
        pass

    @property
    def sample_dim(self):
      # y + beta + sigma
      return self._N  + self._p + 1

    @property
    def theta_indices(self):
        return onp.arange(self._N, self._N + self._p + 1)

    def log_prior(self, beta=None, gamma=None, k=None, sigma=None):
        if beta is None:
            beta = self._beta
        if gamma is None:
            gamma = self._gamma
        if k is None:
            k = self._k
        if sigma is None:
            sigma = self._sigma
        return - scipy.special.loggamma(self._p+1) + scipy.special.loggamma(k+1) + scipy.special.loggamma(self._p-k+1) - self._Lambda + k*onp.log(self._Lambda) - scipy.special.loggamma(k+1) + \
                scipy.stats.laplace.logpdf(x=beta[gamma, :], scale=self._tau).sum() + scipy.stats.invgamma.logpdf(x=self._sigma**2, a=self._alpha_sigma2, scale=self._beta_sigma2)

    def log_likelihood(self, beta=None, sigma=None, y=None, return_components=False):
        if beta is None:
            beta = self._beta
        if sigma is None:
            sigma = self._sigma
        if y is None:
            y = self._y
        l = scipy.stats.norm.logpdf(x=y, loc=self._X@beta, scale=sigma)
        if return_components == False:
            l = l.sum()
        return l

    def log_joint(self, beta=None, gamma=None, k=None, sigma=None):
        if beta is None:
            beta = self._beta
        if gamma is None:
            gamma = self._gamma
        if k is None:
            k = self._k
        if sigma is None:
            sigma = self._sigma
        l_prior = self.log_prior(beta=beta, gamma=gamma, k=k, sigma=sigma)
        l_likelihood = self.log_likelihood(beta=beta, sigma=sigma)
        return l_prior + l_likelihood

    def drawData(self, rng=None):
        if rng is None:
            rng = self._rng_s
        self._X = rng.normal(size=[self._N, self._p])
        return self._X

    def drawPrior(self, rng=None):
        if rng is None:
            rng = self._rng_s
      
        self._sigma = onp.sqrt(scipy.stats.invgamma(a=self._alpha_sigma2, scale=self._beta_sigma2).rvs())
      
        self._beta = onp.zeros(shape=[self._p, 1])
        self._k = rng.choice(a=onp.arange(1, self._p+1), p=self._pmf_k)

        self._gamma = rng.choice(self._p, size=self._k, replace=False)
        self._beta[self._gamma, :] = rng.laplace(
            scale=self._tau, size=[self._k, 1])
        return onp.hstack([self._beta.flatten(), self._sigma])

    def drawLikelihood(self, rng=None):
        if rng is None:
            rng = self._rng_s
        self._y = rng.normal(loc=self._X @ self._beta,
                           scale=self._sigma).reshape(self._N, 1)
        return self._y.flatten()

    def drawPosterior(self, rng=None):
        if rng is None:
            rng = self._rng_s
      
        # Birth-Death
        j, k_proposal, gamma_proposal, beta_proposal = self.getBirthDeathProposal(rng)
      
        if rng.choice(2) == 1:
            self._sigma = onp.sqrt(scipy.stats.invgamma(a=self._alpha_sigma2 + 0.5*self._N, scale=self._beta_sigma2 + 0.5*((self._y-(self._X@self._beta))**2).sum()).rvs())
            self.updateMH(j, k_proposal, gamma_proposal, beta_proposal, rng)
        else:
            self.updateMH(j, k_proposal, gamma_proposal, beta_proposal, rng)
            self._sigma = onp.sqrt(scipy.stats.invgamma(a=self._alpha_sigma2 + 0.5*self._N, scale=self._beta_sigma2 + 0.5*((self._y-(self._X@self._beta))**2).sum()).rvs())
        
        return onp.hstack([self._beta.flatten(), self._sigma])

    def getBirthDeathProposal(self, rng):
        beta_proposal = self._beta.copy()
        if self._p == 1:
            k_proposal = self._k
        elif self._k == 1:
            k_proposal = self._k + rng.choice([0, 1])
        elif self._k == self._p:
            k_proposal = self._k + rng.choice([-1, 0])
        else:
            k_proposal = self._k + rng.choice([-1, 0, 1])

        if k_proposal == self._k:  # update
            j = rng.choice(self._gamma)
            gamma_proposal = self._gamma
            beta_proposal[j, :] += rng.normal(scale=self._epsilon_update)
        elif k_proposal == self._k + 1:  # birth
            j = rng.choice(onp.setdiff1d(onp.arange(self._p), self._gamma))
            gamma_proposal = onp.hstack([self._gamma, j])
            beta_proposal[j, :] = rng.normal(scale=self._epsilon_birth)
        elif k_proposal == self._k - 1:  # death
            j = rng.choice(self._gamma)
            gamma_proposal = self._gamma[self._gamma != j]
            beta_proposal[j, :] = 0.
        return j, k_proposal, gamma_proposal, beta_proposal

    def gammaProposal_prob(self, gamma, gamma_proposal):
        k = gamma.shape[0]
        k_proposal = gamma_proposal.shape[0]
        prob = 0.
        if self._p == 1:
            return prob
        
        num_gamma_shared = onp.intersect1d(gamma, gamma_proposal).shape[0]
        if k == 1 and num_gamma_shared == 1:
            if k_proposal == k+1:
                  prob = 0.5 * 1./(self._p - k)
            elif k_proposal == k:
                  prob = 0.5
        elif 1 < k and k < self._p and onp.abs(num_gamma_shared - k) <= 1:
            if k_proposal == k+1:
                prob = 1./3. * 1./(self._p - k)
            elif k_proposal == k:
                prob = 1./3.
            elif k_proposal == k-1:
                prob = 1./3. * 1./k
        elif k == self._p and num_gamma_shared == self._p-1:
            if k_proposal == k:
                prob = 0.5
            elif k_proposal == k-1:
                prob = 0.5 * 1./k
        return prob

    def updateMH(self, j, k_proposal, gamma_proposal, beta_proposal, rng):
        if k_proposal == self._k:  # update
            MH_augment = 0.
        elif k_proposal == self._k + 1:  # birth
            MH_augment = onp.log(self.gammaProposal_prob(gamma_proposal, self._gamma)) - onp.log(self.gammaProposal_prob(
                                self._gamma, gamma_proposal)) - float(scipy.stats.norm.logpdf(beta_proposal[j, :], scale=self._epsilon_birth))
        elif k_proposal == self._k - 1:  # death
            MH_augment = onp.log(self.gammaProposal_prob(gamma_proposal, self._gamma)) - onp.log(self.gammaProposal_prob(
            self._gamma, gamma_proposal)) + float(scipy.stats.norm.logpdf(self._beta[j, :], scale=self._epsilon_birth))

        diff_log_joint = self.log_joint(beta=beta_proposal, gamma=gamma_proposal, k=k_proposal) - self.log_joint()
        threshold = diff_log_joint + MH_augment

        log_u = onp.log(rng.uniform())
        if log_u <= threshold:
            self._k = k_proposal
            self._gamma = gamma_proposal
            self._beta = beta_proposal
        return log_u, threshold
    
    def test_functions(self, samples):
        num_samples = samples.shape[0]
        y = samples[:, :self._N].reshape(num_samples, -1)
        beta = samples[:, self.theta_indices[:-1]].reshape(num_samples, -1)
        sigma = samples[:, self.theta_indices[-1]].reshape(num_samples, -1)
        l = self.log_likelihood(beta=beta.T, sigma=sigma.T, \
                             y = y.T, return_components=True).sum(0).reshape(-1,1)
        return onp.hstack([geweke_functions(samples[:, self.theta_indices]), l])
      
'''
Error 1: forget to include the transition probabilities when calculating the acceptance probabilities for the 'birth' and 'death' moves
'''
class bayes_lasso_sampler_error_1(bayes_lasso_sampler):
    def updateMH(self, j, k_proposal, gamma_proposal, beta_proposal, rng):
        diff_log_joint = self.log_joint(
            beta=beta_proposal, gamma=gamma_proposal, k=k_proposal) - self.log_joint()
        threshold = diff_log_joint

        log_u = onp.log(rng.uniform())
        if log_u <= threshold:
            self._k = k_proposal
            self._gamma = gamma_proposal
            self._beta = beta_proposal
        return log_u, threshold


'''
Error 2: drop a '+1' in the log-prior Poisson calculation
'''
class bayes_lasso_sampler_error_2(bayes_lasso_sampler):
    def log_prior(self, beta=None, gamma=None, k=None, sigma=None):
        if beta is None:
            beta = self._beta
        if gamma is None:
            gamma = self._gamma
        if k is None:
            k = self._k
        if sigma is None:
            sigma = self._sigma
#         return - scipy.special.loggamma(self._p+1) + scipy.special.loggamma(k+1) + scipy.special.loggamma(self._p-k+1) - self._Lambda + k*onp.log(self._Lambda) - scipy.special.loggamma(k+1) + \
#                 scipy.stats.laplace.logpdf(x=beta[gamma, :], scale=self._tau).sum() + scipy.stats.invgamma.logpdf(x=self._sigma**2, a=self._alpha_sigma2, scale=self._beta_sigma2) # correct
        return - scipy.special.loggamma(self._p+1) + scipy.special.loggamma(k+1) + scipy.special.loggamma(self._p-k+1) - self._Lambda + k*onp.log(self._Lambda) - scipy.special.loggamma(k) + \
                scipy.stats.laplace.logpdf(x=beta[gamma, :], scale=self._tau).sum() + scipy.stats.invgamma.logpdf(x=self._sigma**2, a=self._alpha_sigma2, scale=self._beta_sigma2) # error
