# GradWindow project update playbook

Project updates should give applicants something useful before asking for attention.
Publish when GradWindow adds meaningful coverage, a new application cycle, or a
feature that removes work for applicants. Small parser refactors and routine data
refreshes do not need an announcement.

The first milestone post is the
[v0.3.0 release](https://github.com/lione12138/qs-master-applications/releases/tag/v0.3.0).

## Before publishing

1. Run `gradwindow validate` and copy the verified counts from its output.
2. Describe the scope precisely. "The university index covers the QS Top 200"
   does not mean every programme has a verified deadline.
3. Name one concrete improvement and link to a page where readers can use it.
4. Include the official-source limitation. Applicants should always check the
   university page before submitting.
5. Put the Star invitation at the end, after the useful information.

## GitHub release template

```markdown
# [Specific milestone or feature]

[One sentence explaining what changed and who it helps.]

## What changed

- [Verified count or concrete feature]
- [Second concrete improvement]
- [Link to an example in the live tracker]

## A note on coverage

[Say what is complete, what is still growing, and how official dates differ from
estimates. Do not turn catalogue coverage into a deadline coverage claim.]

Try it: https://gradwindow.com/

Found an incorrect date? [Report it with the official source](https://github.com/lione12138/qs-master-applications/issues/new?template=report-data-error.yml).

If this saved you some deadline hunting, a GitHub star helps other applicants find
the project.
```

## Chinese community post

```text
我做了一个硕士申请截止日期追踪器，叫 GradWindow。

起因很简单：查申请时间经常要在学校官网、学院页面和项目页面之间来回翻，
而且官网日期和往年日期很容易混在一起。

这次更新：[用一句话说明真实更新，例如“QS 前 200 大学索引已经补齐”]。

目前数据包括：
- [经验证的大学 / 项目 / 申请窗口数量]
- 每条正式窗口都有大学官网来源
- 预测日期会单独标注，不会伪装成官方日期
- 可以按学校、项目、入学季和申请人类别筛选，也可以加入日历

网站：https://gradwindow.com/
源码：https://github.com/lione12138/qs-master-applications

项目覆盖还在增加。如果你发现日期不对，最好带上官网链接提 issue，我会核对。
如果它确实帮你少翻了几个官网，再考虑点个 Star 就好。
```

## English community post

```text
I built GradWindow after getting tired of checking a university page, a faculty
page, and a programme page just to work out one application deadline.

This update: [describe one real milestone in a sentence].

The tracker currently has [verified counts]. Published windows link to the
official university source. Estimates are labelled separately because last
year's date is useful for planning, but it is not an official deadline.

You can filter by university, programme, intake, and applicant category, then add
a deadline to your calendar: https://gradwindow.com/

Coverage is still growing. If you spot a wrong date, please send the official
source in an issue. If the tracker saves you time, a Star helps other applicants
find it: https://github.com/lione12138/qs-master-applications
```

## Short update

```text
[Concrete milestone] is now live in GradWindow.

[One useful detail or verified count.]

Search the tracker: https://gradwindow.com/
Source and data: https://github.com/lione12138/qs-master-applications
```

## Distribution checklist

- Publish the GitHub release first so every later post has a stable source link.
- Use one screenshot or the social preview image. Do not attach a collage.
- Change the opening sentence for each community instead of pasting the same ad.
- Answer data questions with official links. A correction is more useful than a
  defensive reply.
- Do not bump old posts or post routine updates just to ask for Stars.
- Record the date, community, post URL, and resulting site visits before deciding
  where to post the next update.

