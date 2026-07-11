# Fit models

## Linear fit

```python
from sklearn.linear_model import LinearRegression
model = LinearRegression().fit(x.reshape(-1,1), y)
k, b = model.coef_[0], model.intercept_
r2 = model.score(x.reshape(-1,1), y)
label = f"y = {k:.2e}x + {b:.2e}  (R²={r2:.3f})"
```

Minimum 3 valid points required.

## Reciprocal fit

```python
from scipy.optimize import curve_fit
def recip_model(x, k, a, c): return c / (k*x + a)
# bootstrap p0 from 1/y linear regression, then refine with curve_fit
```

Minimum 5 valid points required.

## Binned stats (for errorbar style)

```python
bins = np.linspace(x.min(), x.max(), 11)  # 10 bins
# compute mean ± std per bin, min 2 points
```

The executable reference implementation of all three lives in
`data_analysis_workspace/shared/generate_figures.py` (see the style contract's
source-of-truth rule) — mirror it exactly in bespoke scripts.
