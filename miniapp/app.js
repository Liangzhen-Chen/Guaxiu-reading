const API = "https://122.51.236.219:8000"

App({
  globalData: { token: "", user: null },

  onLaunch() {
    const t = wx.getStorageSync("token")
    if (t) this.globalData.token = t
  },

  wxLogin(cb) {
    wx.login({
      success: res => {
        wx.request({
          url: API + "/api/auth/wechat-login",
          method: "POST",
          data: { code: res.code },
          success: r => {
            if (r.statusCode === 200) {
              const d = r.data
              wx.setStorageSync("token", d.access_token)
              this.globalData.token = d.access_token
              this.globalData.user = d.user
              cb && cb(null, d)
            } else {
              cb && cb(r.data)
            }
          },
          fail: err => cb && cb(err)
        })
      }
    })
  }
})
