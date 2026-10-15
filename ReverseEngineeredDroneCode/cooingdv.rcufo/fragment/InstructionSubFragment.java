package com.cooingdv.rcufo.fragment;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import com.cooingdv.rcufo.C3033R;
import com.cooingdv.rcufo.base.BaseFragment;
import com.cooingdv.rcufo.tools.IConstants;

/* JADX INFO: loaded from: classes2.dex */
public class InstructionSubFragment extends BaseFragment {
    private ImageView imageView;

    @Override // com.cooingdv.rcufo.base.BaseFragment, androidx.fragment.app.Fragment
    public View onCreateView(LayoutInflater layoutInflater, ViewGroup viewGroup, Bundle bundle) {
        View viewInflate = layoutInflater.inflate(C3033R.layout.fragment_insturction_sub, viewGroup, false);
        this.imageView = (ImageView) viewInflate.findViewById(C3033R.id.iv_image);
        return viewInflate;
    }

    @Override // androidx.fragment.app.Fragment
    public void onActivityCreated(Bundle bundle) {
        Bundle bundle2;
        int i;
        super.onActivityCreated(bundle);
        if (getActivity() == null || (bundle2 = getBundle()) == null || (i = bundle2.getInt(IConstants.KEY_RES_ID, -1)) == -1) {
            return;
        }
        this.imageView.setImageResource(i);
    }
}
