/* Optional exact banded RMS-Euclidean DTW. No global mutable state. */
#include <math.h>
#include <stddef.h>

int sonara_dtw_abi(void) { return 1; }

double sonara_dtw(const double *a, int n, const double *b, int m, int dims, double band) {
    if (n<1 || m<1 || n>600 || m>600 || dims<1 || dims>128 ||
        !isfinite(band) || band<0 || band>1) return INFINITY;
    double costs[2][601];
    int lengths[2][601];
    for (int j=0;j<=m;j++) { costs[0][j]=INFINITY; lengths[0][j]=0; }
    costs[0][0]=0;
    int width=(int)ceil(band*(n>m?n:m));
    int difference=n>m?n-m:m-n;
    if (width<difference) width=difference;
    int previous=0, current=1;
    for (int i=1;i<=n;i++) {
        for (int j=0;j<=m;j++) { costs[current][j]=INFINITY; lengths[current][j]=0; }
        int low=i-width>1?i-width:1;
        int high=i+width<m?i+width:m;
        for (int j=low;j<=high;j++) {
            double distance=0;
            for (int k=0;k<dims;k++) {
                double delta=a[(size_t)(i-1)*dims+k]-b[(size_t)(j-1)*dims+k];
                distance+=delta*delta;
            }
            distance=sqrt(distance/dims);
            double best=costs[previous][j-1];
            int length=lengths[previous][j-1];
            if (costs[previous][j]<best) { best=costs[previous][j]; length=lengths[previous][j]; }
            if (costs[current][j-1]<best) { best=costs[current][j-1]; length=lengths[current][j-1]; }
            costs[current][j]=best+distance;
            lengths[current][j]=length+1;
        }
        int swap=previous;previous=current;current=swap;
    }
    return lengths[previous][m]>0 ? costs[previous][m]/lengths[previous][m] : INFINITY;
}
