package com.cooingdv.rcufo.base;

import android.os.Bundle;
import android.text.TextUtils;
import android.util.Log;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Toast;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.fragment.app.Fragment;
import androidx.fragment.app.FragmentManager;
import androidx.fragment.app.FragmentTransaction;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.tools.FlyCommand;
import com.cooingdv.rcufo.tools.IActions;
import com.cooingdv.rcufo.tools.IConstants;
import java.util.ArrayList;
import java.util.List;

/* JADX INFO: loaded from: classes2.dex */
public class BaseFragment extends Fragment implements IConstants, IActions, FlyCommand {
    private Bundle bundle;
    public MainApplication mApplication;
    private Toast mToast;
    public String TAG = getClass().getSimpleName();
    private int REQUEST_CODE_PERMISSION = 153;

    @Override // androidx.fragment.app.Fragment
    public void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        if (getActivity() != null) {
            this.mApplication = (MainApplication) getActivity().getApplication();
        }
    }

    @Override // androidx.fragment.app.Fragment
    public View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
        return super.onCreateView(layoutInflater, viewGroup, bundle);
    }

    @Override // androidx.fragment.app.Fragment
    public void onResume() {
        super.onResume();
        if (getActivity() == null || this.mApplication != null) {
            return;
        }
        this.mApplication = (MainApplication) getActivity().getApplication();
    }

    @Override // androidx.fragment.app.Fragment
    public void onDetach() {
        super.onDetach();
    }

    public Bundle getBundle() {
        return this.bundle;
    }

    public void setBundle(Bundle bundle) {
        this.bundle = bundle;
    }

    public void showToast(String str, int i) {
        if (getActivity() == null || TextUtils.isEmpty(str) || i < 0) {
            return;
        }
        Toast toast = this.mToast;
        if (toast == null) {
            this.mToast = Toast.makeText(getActivity().getApplicationContext(), str, i);
        } else {
            toast.setText(str);
            this.mToast.setDuration(i);
        }
        this.mToast.setGravity(17, 0, 0);
        this.mToast.show();
    }

    public void showShortToast(String str) {
        showToast(str, 0);
    }

    public void showShortToast(int i) {
        showShortToast(getString(i));
    }

    public void showLongToast(String str) {
        showToast(str, 1);
    }

    public void showLongToast(int i) {
        showLongToast(getString(i));
    }

    public void showCenterToast(String str) {
        Toast toastMakeText = Toast.makeText(getActivity(), str, 0);
        toastMakeText.setGravity(17, 0, -40);
        toastMakeText.show();
    }

    public void changeFragment(int i, Fragment fragment, String str) {
        FragmentManager supportFragmentManager;
        FragmentTransaction fragmentTransactionBeginTransaction;
        if (fragment == null || getActivity() == null || (supportFragmentManager = getActivity().getSupportFragmentManager()) == null || (fragmentTransactionBeginTransaction = supportFragmentManager.beginTransaction()) == null) {
            return;
        }
        if (!TextUtils.isEmpty(str)) {
            fragmentTransactionBeginTransaction.replace(i, fragment, str);
        } else {
            fragmentTransactionBeginTransaction.replace(i, fragment);
        }
        fragmentTransactionBeginTransaction.addToBackStack(null);
        fragmentTransactionBeginTransaction.commitAllowingStateLoss();
    }

    public void requestPermission(String[] strArr, int i) {
        this.REQUEST_CODE_PERMISSION = i;
        if (checkPermissions(strArr)) {
            permissionSuccess(this.REQUEST_CODE_PERMISSION);
        } else {
            List<String> deniedPermissions = getDeniedPermissions(strArr);
            requestPermissions((String[]) deniedPermissions.toArray(new String[deniedPermissions.size()]), this.REQUEST_CODE_PERMISSION);
        }
    }

    private boolean checkPermissions(String[] strArr) {
        for (String str : strArr) {
            if (ContextCompat.checkSelfPermission(getActivity(), str) != 0) {
                return false;
            }
        }
        return true;
    }

    private List<String> getDeniedPermissions(String[] strArr) {
        ArrayList arrayList = new ArrayList();
        for (String str : strArr) {
            if (ContextCompat.checkSelfPermission(getActivity(), str) != 0 || ActivityCompat.shouldShowRequestPermissionRationale(getActivity(), str)) {
                arrayList.add(str);
            }
        }
        return arrayList;
    }

    @Override // androidx.fragment.app.Fragment
    public void onRequestPermissionsResult(int i, String[] strArr, int[] iArr) {
        super.onRequestPermissionsResult(i, strArr, iArr);
        if (i == this.REQUEST_CODE_PERMISSION) {
            if (verifyPermissions(iArr)) {
                permissionSuccess(i);
            } else {
                permissionFail(i);
            }
        }
    }

    private boolean verifyPermissions(int[] iArr) {
        for (int i : iArr) {
            if (i != 0) {
                return false;
            }
        }
        return true;
    }

    public void permissionSuccess(int i) {
        Log.d(this.TAG, "获取权限成功=" + i);
    }

    public void permissionFail(int i) {
        Log.d(this.TAG, "获取权限失败=" + i);
        showShortToast(C3033R.string.please_open_permission);
    }
}
